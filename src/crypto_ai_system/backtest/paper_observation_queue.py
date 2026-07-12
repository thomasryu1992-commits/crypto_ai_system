from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.backtest.paper_trading_candidate_registry import (
    execute_paper_trading_candidate_registry,
)

STEP209_STATUS_OK = "STEP209_V5_PAPER_OBSERVATION_QUEUE_OK"
STEP209_VALIDATION_OK = "STEP209_V5_PAPER_OBSERVATION_QUEUE_VALIDATION_OK"

OBSERVATION_MODE = "TRACK_SIGNALS_ONLY"
DEFAULT_OBSERVATION_DAYS = 28
DEFAULT_MIN_PAPER_TRADES = 20


@dataclass
class PaperObservationQueueItem:
    observation_id: str
    registry_id: str
    candidate_rank: int
    comparison_group: str
    timeframe: str
    rr: float
    side: str
    permission_mode: str
    source_registry_status: str
    observation_status: str
    observation_mode: str
    observation_days_required: int
    min_paper_trades_required: int
    remaining_observation_days: int
    paper_tracking_enabled: bool
    paper_signal_observation_enabled: bool
    paper_order_execution_allowed: bool
    live_trading_allowed: bool
    auto_strategy_promotion: bool
    requires_operator_review: bool
    candidate_score: float
    blockers: List[str]
    safety_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step209PaperObservationQueueResult:
    status: str
    root: str
    source_step208_result_path: str
    queue_json_path: str
    queue_csv_path: str
    queue_markdown_path: str
    latest_result_path: str
    queue_item_count: int
    active_observation_count: int
    watchlist_observation_count: int
    blocked_observation_count: int
    paper_observation_queue_created: bool
    paper_tracking_enabled: bool
    paper_signal_observation_enabled: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    source_policy_enforced: bool
    operator_review_required: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    queue_items: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step209ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step208_present: bool
    queue_json_exists: bool
    queue_csv_exists: bool
    queue_markdown_exists: bool
    queue_items_present: bool
    paper_observation_queue_created: bool
    paper_tracking_enabled: bool
    paper_signal_observation_enabled: bool
    no_paper_order_execution: bool
    no_paper_trade_execution: bool
    no_auto_promotion: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    source_policy_enforced: bool
    operator_review_required: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["observation_id", "registry_id", "observation_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["blockers"] = "|".join(out.get("blockers", []))
            writer.writerow(out)


def _ensure_step208(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step208_paper_trading_candidate_registry_latest.json"
    if not path.exists():
        execute_paper_trading_candidate_registry(root, write_output=True)
    return _load_json(path)


def _observation_status(candidate: Dict[str, Any]) -> tuple[str, List[str], bool]:
    registry_status = str(candidate.get("registry_status", ""))
    blockers = list(candidate.get("blockers", []) or [])
    tracking_enabled = candidate.get("paper_tracking_enabled") is True
    if not tracking_enabled:
        return "PAPER_OBSERVATION_BLOCKED", blockers or ["PAPER_TRACKING_NOT_ENABLED"], False
    if registry_status == "PAPER_CANDIDATE_REVIEW_ONLY" and not blockers:
        return "PAPER_OBSERVATION_READY", [], True
    if registry_status == "PAPER_CANDIDATE_WATCHLIST":
        watchlist_blockers = blockers or ["WATCHLIST_REVIEW_REQUIRED"]
        if "WATCHLIST_REVIEW_REQUIRED" not in watchlist_blockers:
            watchlist_blockers.append("WATCHLIST_REVIEW_REQUIRED")
        return "PAPER_OBSERVATION_WATCHLIST", watchlist_blockers, True
    return "PAPER_OBSERVATION_BLOCKED", blockers or ["SOURCE_CANDIDATE_NOT_OBSERVABLE"], False


def _build_queue_items(candidates: List[Dict[str, Any]]) -> List[PaperObservationQueueItem]:
    queue: List[PaperObservationQueueItem] = []
    for idx, candidate in enumerate(candidates, start=1):
        registry_id = str(candidate.get("registry_id", f"paper_candidate_{idx:02d}"))
        group = str(candidate.get("comparison_group", f"candidate_{idx:02d}"))
        status, blockers, signal_observation_enabled = _observation_status(candidate)
        observation_id = "obs_{idx:02d}_{digest}".format(
            idx=idx,
            digest=hashlib.sha1(f"{registry_id}:{group}".encode("utf-8")).hexdigest()[:8],
        )
        observation_days = int(candidate.get("paper_observation_days_required", DEFAULT_OBSERVATION_DAYS))
        min_trades = int(candidate.get("min_paper_trades_required", DEFAULT_MIN_PAPER_TRADES))
        queue.append(
            PaperObservationQueueItem(
                observation_id=observation_id,
                registry_id=registry_id,
                candidate_rank=int(candidate.get("candidate_rank", idx)),
                comparison_group=group,
                timeframe=str(candidate.get("timeframe", "")),
                rr=float(candidate.get("rr", 0.0)),
                side=str(candidate.get("side", "")),
                permission_mode=str(candidate.get("permission_mode", "")),
                source_registry_status=str(candidate.get("registry_status", "")),
                observation_status=status,
                observation_mode=OBSERVATION_MODE,
                observation_days_required=observation_days,
                min_paper_trades_required=min_trades,
                remaining_observation_days=observation_days,
                paper_tracking_enabled=candidate.get("paper_tracking_enabled") is True,
                paper_signal_observation_enabled=signal_observation_enabled,
                paper_order_execution_allowed=False,
                live_trading_allowed=False,
                auto_strategy_promotion=False,
                requires_operator_review=True,
                candidate_score=float(candidate.get("expanded_oos_score", 0.0)),
                blockers=blockers,
                safety_notes="Queue is for paper signal observation only. It cannot place paper orders, call live adapters, or promote strategies automatically.",
            )
        )
    return queue


def _blocker_summary(items: List[PaperObservationQueueItem]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in items:
        if not item.blockers:
            summary["NO_BLOCKER"] = summary.get("NO_BLOCKER", 0) + 1
        for blocker in item.blockers:
            summary[blocker] = summary.get(blocker, 0) + 1
    return dict(sorted(summary.items()))


def _result_hash_payload(result: Step209PaperObservationQueueResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step209PaperObservationQueueResult, items: List[PaperObservationQueueItem]) -> str:
    lines = [
        "# Step209 v5 Paper Observation Queue",
        "",
        "This queue converts Step208 paper-trading candidates into track-only observation items.",
        "It does not enable paper order execution, live trading, Telegram real sends, or automatic strategy promotion.",
        "",
        "## Summary",
        f"- queue_item_count: {result.queue_item_count}",
        f"- active_observation_count: {result.active_observation_count}",
        f"- watchlist_observation_count: {result.watchlist_observation_count}",
        f"- blocked_observation_count: {result.blocked_observation_count}",
        f"- paper_signal_observation_enabled: {result.paper_signal_observation_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- paper_trade_execution_enabled: {result.paper_trade_execution_enabled}",
        f"- source_policy_enforced: {result.source_policy_enforced}",
        f"- auto_strategy_promotion: {result.auto_strategy_promotion}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Queue Items",
    ]
    for item in items:
        blockers = ", ".join(item.blockers) if item.blockers else "NO_BLOCKER"
        lines.extend(
            [
                "",
                f"### {item.observation_id} - {item.comparison_group}",
                f"- registry_id: {item.registry_id}",
                f"- status: {item.observation_status}",
                f"- timeframe: {item.timeframe}",
                f"- side: {item.side}",
                f"- rr: {item.rr}",
                f"- permission_mode: {item.permission_mode}",
                f"- observation_days_required: {item.observation_days_required}",
                f"- min_paper_trades_required: {item.min_paper_trades_required}",
                f"- paper_order_execution_allowed: {item.paper_order_execution_allowed}",
                f"- blockers: {blockers}",
            ]
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step209 is an observation queue only.",
            "- Every item requires operator review before any future execution-oriented step.",
            "- No external API calls, live adapter calls, Telegram real sends, or live order execution are performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_observation_queue(root: str | Path, *, write_output: bool = True) -> Step209PaperObservationQueueResult:
    root_path = Path(root).resolve()
    step208_path = root_path / "storage/latest/step208_paper_trading_candidate_registry_latest.json"
    step208 = _ensure_step208(root_path)
    candidates = list(step208.get("candidates", []) or [])
    queue_items = _build_queue_items(candidates)

    queue_json = root_path / "data/reports/step209_paper_observation_queue.json"
    queue_csv = root_path / "data/reports/step209_paper_observation_queue.csv"
    markdown = root_path / "data/reports/step209_paper_observation_queue_report.md"
    latest = root_path / "storage/latest/step209_paper_observation_queue_latest.json"

    result = Step209PaperObservationQueueResult(
        status=STEP209_STATUS_OK,
        root=str(root_path),
        source_step208_result_path=str(step208_path),
        queue_json_path=str(queue_json),
        queue_csv_path=str(queue_csv),
        queue_markdown_path=str(markdown),
        latest_result_path=str(latest),
        queue_item_count=len(queue_items),
        active_observation_count=sum(1 for item in queue_items if item.observation_status == "PAPER_OBSERVATION_READY"),
        watchlist_observation_count=sum(1 for item in queue_items if item.observation_status == "PAPER_OBSERVATION_WATCHLIST"),
        blocked_observation_count=sum(1 for item in queue_items if item.observation_status == "PAPER_OBSERVATION_BLOCKED"),
        paper_observation_queue_created=True,
        paper_tracking_enabled=bool(queue_items),
        paper_signal_observation_enabled=any(item.paper_signal_observation_enabled for item in queue_items),
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        source_policy_enforced=True,
        operator_review_required=True,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        queue_items=[item.to_dict() for item in queue_items],
        blocker_summary=_blocker_summary(queue_items),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(queue_json, {"queue_items": [item.to_dict() for item in queue_items]})
        _write_csv(queue_csv, [item.to_dict() for item in queue_items])
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(_render_markdown(result, queue_items), encoding="utf-8")
        _write_json(latest, result.to_dict())
    return result


def validate_paper_observation_queue(root: str | Path) -> Step209ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step209_paper_observation_queue_latest.json"
    if not result_path.exists():
        execute_paper_observation_queue(root_path, write_output=True)
    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    queue_items = list(payload.get("queue_items", []) or [])
    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step208_present": Path(payload.get("source_step208_result_path", "")).exists(),
        "queue_json_exists": Path(payload.get("queue_json_path", "")).exists(),
        "queue_csv_exists": Path(payload.get("queue_csv_path", "")).exists(),
        "queue_markdown_exists": Path(payload.get("queue_markdown_path", "")).exists(),
        "queue_items_present": int(payload.get("queue_item_count", 0)) > 0,
        "paper_observation_queue_created": payload.get("paper_observation_queue_created") is True,
        "paper_tracking_enabled": payload.get("paper_tracking_enabled") is True,
        "paper_signal_observation_enabled": payload.get("paper_signal_observation_enabled") is True,
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False and all(item.get("paper_order_execution_allowed") is False for item in queue_items),
        "no_paper_trade_execution": payload.get("paper_trade_execution_enabled") is False,
        "no_auto_promotion": payload.get("auto_strategy_promotion") is False and all(item.get("auto_strategy_promotion") is False for item in queue_items),
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False and payload.get("real_adapter_call_performed") is False and payload.get("telegram_real_send") is False,
        "source_policy_enforced": payload.get("source_policy_enforced") is True,
        "operator_review_required": payload.get("operator_review_required") is True and all(item.get("requires_operator_review") is True for item in queue_items),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step209ValidationResult(
        status=STEP209_VALIDATION_OK if not failures else "STEP209_V5_PAPER_OBSERVATION_QUEUE_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
