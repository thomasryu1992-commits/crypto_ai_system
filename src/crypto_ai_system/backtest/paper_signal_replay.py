from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from crypto_ai_system.backtest.paper_observation_queue import (
    execute_paper_observation_queue,
)
from crypto_ai_system.backtest.strategy_matrix_execution import (
    MAX_HOLD_BARS,
    _compute_metrics,
    _load_price_frame,
    _permission_gate_allows,
    _price_structure_signal,
    _simulate_trade,
)

STEP210_STATUS_OK = "STEP210_V5_PAPER_SIGNAL_REPLAY_OK"
STEP210_VALIDATION_OK = "STEP210_V5_PAPER_SIGNAL_REPLAY_VALIDATION_OK"

ELIGIBLE_OBSERVATION_STATUSES = {
    "PAPER_OBSERVATION_READY",
    "PAPER_OBSERVATION_WATCHLIST",
}

MIN_REPLAY_TRADES = 20
MIN_EXPECTANCY_R = 0.0
MIN_PROFIT_FACTOR = 1.0
MAX_DRAWDOWN_ABS_PCT = 20.0


@dataclass
class PaperSignalReplayEvent:
    event_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    timeframe: str
    side: str
    rr: float
    permission_mode: str
    source_observation_status: str
    signal_timestamp: str
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    stop_price: float
    target_price: float
    r_multiple: float
    mfe_r: float
    mae_r: float
    exit_reason: str
    entry_regime: str
    paper_order_created: bool
    paper_order_execution_allowed: bool
    live_order_executed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperSignalReplaySummary:
    observation_id: str
    registry_id: str
    comparison_group: str
    timeframe: str
    side: str
    rr: float
    permission_mode: str
    source_observation_status: str
    price_structure_signal_count: int
    permission_block_count: int
    simulated_trade_count: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_pct: float
    average_r: float
    average_mfe_r: float
    average_mae_r: float
    trade_frequency_per_day: float
    replay_status: str
    blockers: List[str]
    recommendation: str
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    promotion_allowed: bool
    live_trading_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step210PaperSignalReplayResult:
    status: str
    root: str
    source_step209_result_path: str
    replay_events_path: str
    summary_json_path: str
    summary_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    queue_item_count: int
    eligible_queue_item_count: int
    blocked_queue_item_count: int
    replay_event_count: int
    replay_summary_count: int
    review_summary_count: int
    watchlist_summary_count: int
    blocked_summary_count: int
    paper_signal_replay_performed: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    summaries: List[Dict[str, Any]]
    sample_replay_events: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step210ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step209_present: bool
    replay_events_json_exists: bool
    summary_json_exists: bool
    summary_csv_exists: bool
    markdown_report_exists: bool
    has_observation_candidates: bool
    replay_events_exist: bool
    summaries_present: bool
    paper_signal_replay_performed: bool
    no_paper_order_execution: bool
    no_paper_trade_execution: bool
    no_auto_promotion: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    no_production_cutover: bool
    blocking_failure_count: int
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["observation_id", "registry_id", "replay_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["blockers"] = "|".join(out.get("blockers", []))
            writer.writerow(out)


def _ensure_step209(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step209_paper_observation_queue_latest.json"
    if not path.exists():
        execute_paper_observation_queue(root, write_output=True)
    return _load_json(path)


def _is_eligible_queue_item(item: Dict[str, Any]) -> bool:
    return (
        str(item.get("observation_status", "")) in ELIGIBLE_OBSERVATION_STATUSES
        and item.get("paper_signal_observation_enabled") is True
    )


def _summary_blockers(
    *,
    source_observation_status: str,
    simulated_trade_count: int,
    expectancy_r: float,
    profit_factor: float,
    max_drawdown_pct: float,
) -> List[str]:
    blockers: List[str] = []
    if simulated_trade_count <= 0:
        blockers.append("NO_REPLAY_TRADES")
    elif simulated_trade_count < MIN_REPLAY_TRADES:
        blockers.append("REPLAY_TRADE_COUNT_TOO_LOW")
    if expectancy_r < MIN_EXPECTANCY_R:
        blockers.append("REPLAY_EXPECTANCY_BELOW_ZERO")
    if simulated_trade_count > 0 and profit_factor < MIN_PROFIT_FACTOR:
        blockers.append("REPLAY_PROFIT_FACTOR_BELOW_ONE")
    if abs(max_drawdown_pct) > MAX_DRAWDOWN_ABS_PCT:
        blockers.append("REPLAY_DRAWDOWN_ABOVE_LIMIT")
    if source_observation_status == "PAPER_OBSERVATION_WATCHLIST":
        blockers.append("SOURCE_WATCHLIST_REVIEW_REQUIRED")
    return blockers


def _replay_status(blockers: List[str], simulated_trade_count: int, source_observation_status: str) -> Tuple[str, str]:
    if not blockers and source_observation_status == "PAPER_OBSERVATION_READY":
        return (
            "PAPER_REPLAY_REVIEW_ONLY",
            "Candidate produced acceptable replay evidence. Keep it review-only until paper execution dry-run validation is added.",
        )
    if simulated_trade_count > 0:
        return (
            "PAPER_REPLAY_WATCHLIST",
            "Candidate produced replay evidence but still requires more observation or blocker review.",
        )
    return (
        "PAPER_REPLAY_BLOCKED",
        "Candidate did not produce enough replay evidence for future paper execution review.",
    )


def _empty_summary(item: Dict[str, Any], blocker: str) -> PaperSignalReplaySummary:
    status, recommendation = _replay_status([blocker], 0, str(item.get("observation_status", "")))
    return PaperSignalReplaySummary(
        observation_id=str(item.get("observation_id", "")),
        registry_id=str(item.get("registry_id", "")),
        comparison_group=str(item.get("comparison_group", "")),
        timeframe=str(item.get("timeframe", "")),
        side=str(item.get("side", "")),
        rr=float(item.get("rr", 0.0)),
        permission_mode=str(item.get("permission_mode", "")),
        source_observation_status=str(item.get("observation_status", "")),
        price_structure_signal_count=0,
        permission_block_count=0,
        simulated_trade_count=0,
        win_rate=0.0,
        expectancy_r=0.0,
        profit_factor=0.0,
        max_drawdown_pct=0.0,
        average_r=0.0,
        average_mfe_r=0.0,
        average_mae_r=0.0,
        trade_frequency_per_day=0.0,
        replay_status=status,
        blockers=[blocker],
        recommendation=recommendation,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        promotion_allowed=False,
        live_trading_allowed=False,
    )


def _replay_item(root: Path, item: Dict[str, Any]) -> Tuple[List[PaperSignalReplayEvent], PaperSignalReplaySummary]:
    timeframe = str(item.get("timeframe", ""))
    side = str(item.get("side", ""))
    rr = float(item.get("rr", 0.0))
    permission_mode = str(item.get("permission_mode", ""))
    observation_id = str(item.get("observation_id", ""))
    registry_id = str(item.get("registry_id", ""))
    comparison_group = str(item.get("comparison_group", ""))
    source_observation_status = str(item.get("observation_status", ""))

    try:
        df = _load_price_frame(root, timeframe)
    except Exception as exc:
        return [], _empty_summary(item, f"PRICE_FRAME_LOAD_FAILED:{type(exc).__name__}")

    max_hold = MAX_HOLD_BARS.get(timeframe, 48)
    price_structure_signal_count = 0
    permission_block_count = 0
    trades: List[Dict[str, Any]] = []
    events: List[PaperSignalReplayEvent] = []

    for idx in range(30, len(df) - 2):
        row = df.iloc[idx]
        if not _price_structure_signal(row, side):
            continue
        price_structure_signal_count += 1
        if permission_mode == "research_signal_v2_permission_gate" and not _permission_gate_allows(row, side):
            permission_block_count += 1
            continue
        trade = _simulate_trade(df, idx, side, rr, max_hold)
        if not trade:
            continue
        trades.append(trade)
        events.append(
            PaperSignalReplayEvent(
                event_id=f"{observation_id}_event_{len(events) + 1:06d}",
                observation_id=observation_id,
                registry_id=registry_id,
                comparison_group=comparison_group,
                timeframe=timeframe,
                side=side,
                rr=rr,
                permission_mode=permission_mode,
                source_observation_status=source_observation_status,
                signal_timestamp=str(row["timestamp"]),
                entry_timestamp=str(trade.get("entry_timestamp", "")),
                exit_timestamp=str(trade.get("exit_timestamp", "")),
                entry_price=float(trade.get("entry_price", 0.0)),
                stop_price=float(trade.get("stop_price", 0.0)),
                target_price=float(trade.get("target_price", 0.0)),
                r_multiple=float(trade.get("r_multiple", 0.0)),
                mfe_r=float(trade.get("mfe_r", 0.0)),
                mae_r=float(trade.get("mae_r", 0.0)),
                exit_reason=str(trade.get("exit_reason", "")),
                entry_regime=str(trade.get("entry_regime", "")),
                paper_order_created=False,
                paper_order_execution_allowed=False,
                live_order_executed=False,
            )
        )

    exp = SimpleNamespace(
        experiment_id=f"step210_{observation_id}",
        comparison_group=comparison_group,
        timeframe=timeframe,
        rr=rr,
        side=side,
        permission_mode=permission_mode,
    )
    metrics = _compute_metrics(trades, df, exp)

    blockers = _summary_blockers(
        source_observation_status=source_observation_status,
        simulated_trade_count=metrics.total_trades,
        expectancy_r=metrics.expectancy_r,
        profit_factor=metrics.profit_factor,
        max_drawdown_pct=metrics.max_drawdown_pct,
    )
    status, recommendation = _replay_status(blockers, metrics.total_trades, source_observation_status)

    summary = PaperSignalReplaySummary(
        observation_id=observation_id,
        registry_id=registry_id,
        comparison_group=comparison_group,
        timeframe=timeframe,
        side=side,
        rr=rr,
        permission_mode=permission_mode,
        source_observation_status=source_observation_status,
        price_structure_signal_count=price_structure_signal_count,
        permission_block_count=permission_block_count,
        simulated_trade_count=metrics.total_trades,
        win_rate=float(metrics.win_rate),
        expectancy_r=float(metrics.expectancy_r),
        profit_factor=float(metrics.profit_factor),
        max_drawdown_pct=float(metrics.max_drawdown_pct),
        average_r=float(metrics.average_r),
        average_mfe_r=float(metrics.mfe_r),
        average_mae_r=float(metrics.mae_r),
        trade_frequency_per_day=float(metrics.trade_frequency_per_day),
        replay_status=status,
        blockers=blockers,
        recommendation=recommendation,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        promotion_allowed=False,
        live_trading_allowed=False,
    )
    return events, summary


def _blocker_summary(summaries: List[PaperSignalReplaySummary]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for summary in summaries:
        if not summary.blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in summary.blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step210PaperSignalReplayResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step210PaperSignalReplayResult) -> str:
    lines = [
        "# Step210 v5 Paper Signal Replay",
        "",
        "Step210 replays Step209 observation queue candidates on local BTC price CSV data.",
        "It creates replay evidence only and does not create paper orders, call adapters, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- queue_item_count: {result.queue_item_count}",
        f"- eligible_queue_item_count: {result.eligible_queue_item_count}",
        f"- replay_event_count: {result.replay_event_count}",
        f"- replay_summary_count: {result.replay_summary_count}",
        f"- review_summary_count: {result.review_summary_count}",
        f"- watchlist_summary_count: {result.watchlist_summary_count}",
        f"- blocked_summary_count: {result.blocked_summary_count}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- paper_trade_execution_enabled: {result.paper_trade_execution_enabled}",
        f"- auto_strategy_promotion: {result.auto_strategy_promotion}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Candidate summaries",
    ]
    for summary in result.summaries:
        blockers = ", ".join(summary.get("blockers", [])) if summary.get("blockers") else "NO_BLOCKER"
        lines.append(
            "- `{group}` {side} {tf} RR {rr}: status={status}, trades={trades}, "
            "expectancy={expectancy:.4f}, pf={pf:.2f}, blockers={blockers}".format(
                group=summary.get("comparison_group", ""),
                side=summary.get("side", ""),
                tf=summary.get("timeframe", ""),
                rr=summary.get("rr", 0.0),
                status=summary.get("replay_status", ""),
                trades=summary.get("simulated_trade_count", 0),
                expectancy=float(summary.get("expectancy_r", 0.0)),
                pf=float(summary.get("profit_factor", 0.0)),
                blockers=blockers,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step210 is replay and observation only.",
            "- `promotion_allowed` remains false for every candidate.",
            "- Paper order execution and live execution remain disabled.",
            "- External API calls and real adapter calls are not performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_signal_replay(root: str | Path, *, write_output: bool = True) -> Step210PaperSignalReplayResult:
    root_path = Path(root).resolve()
    step209_path = root_path / "storage/latest/step209_paper_observation_queue_latest.json"
    step209 = _ensure_step209(root_path)
    queue_items = list(step209.get("queue_items", []) or [])
    eligible_items = [item for item in queue_items if _is_eligible_queue_item(item)]

    all_events: List[PaperSignalReplayEvent] = []
    summaries: List[PaperSignalReplaySummary] = []
    for item in eligible_items:
        events, summary = _replay_item(root_path, item)
        all_events.extend(events)
        summaries.append(summary)

    replay_events_path = root_path / "data/reports/step210_paper_signal_replay_events.json"
    summary_json_path = root_path / "data/reports/step210_paper_signal_replay_summary.json"
    summary_csv_path = root_path / "data/reports/step210_paper_signal_replay_summary.csv"
    markdown_report_path = root_path / "data/reports/step210_paper_signal_replay_report.md"
    latest_result_path = root_path / "storage/latest/step210_paper_signal_replay_latest.json"

    summary_dicts = [summary.to_dict() for summary in summaries]
    event_dicts = [event.to_dict() for event in all_events]

    result = Step210PaperSignalReplayResult(
        status=STEP210_STATUS_OK,
        root=str(root_path),
        source_step209_result_path=str(step209_path),
        replay_events_path=str(replay_events_path),
        summary_json_path=str(summary_json_path),
        summary_csv_path=str(summary_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        queue_item_count=len(queue_items),
        eligible_queue_item_count=len(eligible_items),
        blocked_queue_item_count=max(0, len(queue_items) - len(eligible_items)),
        replay_event_count=len(all_events),
        replay_summary_count=len(summaries),
        review_summary_count=sum(1 for summary in summaries if summary.replay_status == "PAPER_REPLAY_REVIEW_ONLY"),
        watchlist_summary_count=sum(1 for summary in summaries if summary.replay_status == "PAPER_REPLAY_WATCHLIST"),
        blocked_summary_count=sum(1 for summary in summaries if summary.replay_status == "PAPER_REPLAY_BLOCKED"),
        paper_signal_replay_performed=bool(eligible_items),
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        summaries=summary_dicts,
        sample_replay_events=event_dicts[:100],
        blocker_summary=_blocker_summary(summaries),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(replay_events_path, {"events": event_dicts})
        _write_json(summary_json_path, {"summaries": summary_dicts})
        _write_csv(summary_csv_path, summary_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_signal_replay(root: str | Path) -> Step210ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step210_paper_signal_replay_latest.json"
    if not result_path.exists():
        execute_paper_signal_replay(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))

    event_path = Path(payload.get("replay_events_path", ""))
    event_count = 0
    if event_path.exists():
        event_count = len(_load_json(event_path).get("events", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step209_present": Path(payload.get("source_step209_result_path", "")).exists(),
        "replay_events_json_exists": event_path.exists(),
        "summary_json_exists": Path(payload.get("summary_json_path", "")).exists(),
        "summary_csv_exists": Path(payload.get("summary_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "has_observation_candidates": int(payload.get("eligible_queue_item_count", 0)) > 0,
        "replay_events_exist": event_count > 0,
        "summaries_present": int(payload.get("replay_summary_count", 0)) > 0,
        "paper_signal_replay_performed": payload.get("paper_signal_replay_performed") is True,
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False,
        "no_paper_trade_execution": payload.get("paper_trade_execution_enabled") is False,
        "no_auto_promotion": payload.get("auto_strategy_promotion") is False and all(
            summary.get("promotion_allowed") is False for summary in payload.get("summaries", [])
        ),
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False,
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step210ValidationResult(
        status=STEP210_VALIDATION_OK if not failures else "STEP210_V5_PAPER_SIGNAL_REPLAY_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
