from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.backtest.paper_signal_replay import (
    execute_paper_signal_replay,
)
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    decision_id_from_signal,
    order_intent_id_from_payload,
    chain_complete,
)
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

STEP211_STATUS_OK = "STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_OK"
STEP211_ID_CHAIN_VERSION = ORDER_ID_CHAIN_VERSION
STEP211_VALIDATION_OK = "STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_VALIDATION_OK"

ELIGIBLE_REPLAY_STATUSES = {
    "PAPER_REPLAY_REVIEW_ONLY",
    "PAPER_REPLAY_WATCHLIST",
}

MAX_DRY_RUN_INTENTS_PER_CANDIDATE = 10
DEFAULT_DRY_RUN_NOTIONAL_USD = 100.0


@dataclass
class PaperDryRunOrderIntent:
    dry_run_order_intent_id: str
    order_intent_id: str
    decision_id: str
    risk_gate_id: str
    research_signal_id: str
    profile_id: str
    order_id_chain_version: str
    order_id_chain_source: str
    idempotency_key: str
    source_event_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    mode: str
    status: str
    canonical_symbol: str
    execution_symbol: str
    side: str
    order_type: str
    quantity: float
    dry_run_notional_usd: float
    entry_price: float
    stop_loss: float
    take_profit: float
    rr: float
    timeframe: str
    permission_mode: str
    source_replay_status: str
    source_exit_reason: str
    source_r_multiple: float
    source_entry_regime: str
    created_at_utc: str
    execution_allowed: bool
    paper_order_created: bool
    paper_order_submitted: bool
    paper_order_execution_enabled: bool
    adapter_routing_enabled: bool
    live_order_executed: bool
    safety_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperExecutionDryRunCandidateSummary:
    observation_id: str
    registry_id: str
    comparison_group: str
    timeframe: str
    side: str
    rr: float
    permission_mode: str
    source_replay_status: str
    source_simulated_trade_count: int
    dry_run_intent_count: int
    unique_idempotency_key_count: int
    duplicate_idempotency_key_count: int
    dry_run_bridge_status: str
    blockers: List[str]
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    promotion_allowed: bool
    live_trading_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step211PaperExecutionDryRunBridgeResult:
    status: str
    root: str
    source_step210_result_path: str
    dry_run_intents_path: str
    dry_run_summary_json_path: str
    dry_run_summary_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_replay_summary_count: int
    source_replay_event_count: int
    eligible_replay_summary_count: int
    dry_run_intent_count: int
    candidate_summary_count: int
    ready_candidate_summary_count: int
    watchlist_candidate_summary_count: int
    blocked_candidate_summary_count: int
    paper_execution_dry_run_bridge_created: bool
    paper_order_intent_dry_run_created: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    order_lifecycle_simulation_enabled: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    summaries: List[Dict[str, Any]]
    sample_dry_run_order_intents: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=utc_now_canonical)
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step211ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step210_present: bool
    dry_run_intents_json_exists: bool
    dry_run_summary_json_exists: bool
    dry_run_summary_csv_exists: bool
    markdown_report_exists: bool
    has_eligible_replay_summaries: bool
    dry_run_intents_present: bool
    idempotency_keys_unique: bool
    dry_run_bridge_created: bool
    canonical_order_id_chain_complete: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
    no_order_lifecycle_simulation: bool
    no_auto_promotion: bool
    no_external_api_calls: bool
    no_live_side_effects: bool
    no_production_cutover: bool
    blocking_failure_count: int
    blocking_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return utc_now_canonical()


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
    fieldnames = list(rows[0].keys()) if rows else ["observation_id", "registry_id", "dry_run_bridge_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["blockers"] = "|".join(out.get("blockers", []))
            writer.writerow(out)


def _ensure_step210(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step210_paper_signal_replay_latest.json"
    if not path.exists():
        execute_paper_signal_replay(root, write_output=True)
    return _load_json(path)


def _load_step210_events(step210: Dict[str, Any]) -> List[Dict[str, Any]]:
    events_path = Path(step210.get("replay_events_path", ""))
    if events_path.exists():
        return list(_load_json(events_path).get("events", []) or [])
    return list(step210.get("sample_replay_events", []) or [])


def _eligible_summary(summary: Dict[str, Any]) -> bool:
    return str(summary.get("replay_status", "")) in ELIGIBLE_REPLAY_STATUSES and int(summary.get("simulated_trade_count", 0)) > 0


def _idempotency_key(event: Dict[str, Any], summary: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step211_paper_dry_run",
            str(event.get("event_id", "")),
            str(event.get("observation_id", "")),
            str(event.get("entry_timestamp", "")),
            str(event.get("side", "")),
            str(summary.get("permission_mode", "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _dry_run_order_intent_id(idempotency_key: str, entry_price: float, quantity: float) -> str:
    raw = f"{idempotency_key}|{entry_price:.8f}|{quantity:.8f}"
    return "pdoi_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _quantity_from_notional(entry_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    return round(DEFAULT_DRY_RUN_NOTIONAL_USD / entry_price, 8)


def _source_research_signal_id(event: Dict[str, Any], summary: Dict[str, Any]) -> str:
    existing = str(event.get("research_signal_id") or summary.get("research_signal_id") or "").strip()
    if existing:
        return existing
    return stable_id(
        "research_signal_backfill",
        {
            "source": "step211_step210_replay_backfill_review_only",
            "observation_id": event.get("observation_id") or summary.get("observation_id"),
            "registry_id": event.get("registry_id") or summary.get("registry_id"),
            "comparison_group": event.get("comparison_group") or summary.get("comparison_group"),
            "side": event.get("side") or summary.get("side"),
        },
        24,
    )


def _source_profile_id(event: Dict[str, Any], summary: Dict[str, Any]) -> str:
    existing = str(event.get("profile_id") or summary.get("profile_id") or "").strip()
    if existing:
        return existing
    return stable_id(
        "profile_backfill",
        {
            "source": "step211_step210_replay_backfill_review_only",
            "registry_id": event.get("registry_id") or summary.get("registry_id"),
            "comparison_group": event.get("comparison_group") or summary.get("comparison_group"),
            "permission_mode": event.get("permission_mode") or summary.get("permission_mode"),
        },
        24,
    )


def _source_decision_id(event: Dict[str, Any], summary: Dict[str, Any], research_signal_id: str, profile_id: str) -> str:
    existing = str(event.get("decision_id") or summary.get("decision_id") or "").strip()
    if existing:
        return existing
    return decision_id_from_signal(
        {"research_signal_id": research_signal_id, "profile_id": profile_id, "entry_side": event.get("side") or summary.get("side")},
        {
            "side": event.get("side") or summary.get("side"),
            "source_event_id": event.get("event_id"),
            "observation_id": event.get("observation_id") or summary.get("observation_id"),
            "created_from": "step271_step210_replay_backfill_decision",
        },
    )


def _source_risk_gate_id(event: Dict[str, Any], summary: Dict[str, Any], decision_id: str, research_signal_id: str, profile_id: str) -> str:
    existing = str(event.get("risk_gate_id") or summary.get("risk_gate_id") or "").strip()
    if existing:
        return existing
    return stable_id(
        "risk_gate",
        {
            "chain_version": STEP211_ID_CHAIN_VERSION,
            "source": "step211_step210_replay_backfill_review_only",
            "decision_id": decision_id,
            "research_signal_id": research_signal_id,
            "profile_id": profile_id,
            "permission_mode": event.get("permission_mode") or summary.get("permission_mode"),
        },
        24,
    )


def _build_intent(event: Dict[str, Any], summary: Dict[str, Any]) -> PaperDryRunOrderIntent:
    entry_price = float(event.get("entry_price", 0.0))
    quantity = _quantity_from_notional(entry_price)
    key = _idempotency_key(event, summary)
    research_signal_id = _source_research_signal_id(event, summary)
    profile_id = _source_profile_id(event, summary)
    decision_id = _source_decision_id(event, summary, research_signal_id, profile_id)
    risk_gate_id = _source_risk_gate_id(event, summary, decision_id, research_signal_id, profile_id)
    legacy_intent_id = _dry_run_order_intent_id(key, entry_price, quantity)
    canonical_intent_payload = {
        "dry_run_order_intent_id": legacy_intent_id,
        "decision_id": decision_id,
        "risk_gate_id": risk_gate_id,
        "research_signal_id": research_signal_id,
        "source_event_id": event.get("event_id", ""),
        "observation_id": event.get("observation_id", ""),
        "idempotency_key": key,
        "side": event.get("side", summary.get("side", "")),
        "entry_price": entry_price,
        "quantity": quantity,
    }
    order_intent_id = order_intent_id_from_payload(canonical_intent_payload)
    return PaperDryRunOrderIntent(
        dry_run_order_intent_id=legacy_intent_id,
        order_intent_id=order_intent_id,
        decision_id=decision_id,
        risk_gate_id=risk_gate_id,
        research_signal_id=research_signal_id,
        profile_id=profile_id,
        order_id_chain_version=STEP211_ID_CHAIN_VERSION,
        order_id_chain_source="source_research_signal_or_step210_replay_backfill_review_only",
        idempotency_key=key,
        source_event_id=str(event.get("event_id", "")),
        observation_id=str(event.get("observation_id", "")),
        registry_id=str(event.get("registry_id", "")),
        comparison_group=str(event.get("comparison_group", summary.get("comparison_group", ""))),
        mode="paper_dry_run",
        status="PAPER_ORDER_INTENT_DRY_RUN_CREATED",
        canonical_symbol="BTC-PERP",
        execution_symbol="BTC-USD",
        side=str(event.get("side", summary.get("side", ""))),
        order_type="MARKET",
        quantity=quantity,
        dry_run_notional_usd=DEFAULT_DRY_RUN_NOTIONAL_USD,
        entry_price=entry_price,
        stop_loss=float(event.get("stop_price", 0.0)),
        take_profit=float(event.get("target_price", 0.0)),
        rr=float(event.get("rr", summary.get("rr", 0.0))),
        timeframe=str(event.get("timeframe", summary.get("timeframe", ""))),
        permission_mode=str(event.get("permission_mode", summary.get("permission_mode", ""))),
        source_replay_status=str(summary.get("replay_status", "")),
        source_exit_reason=str(event.get("exit_reason", "")),
        source_r_multiple=float(event.get("r_multiple", 0.0)),
        source_entry_regime=str(event.get("entry_regime", "")),
        created_at_utc=_utc_now(),
        execution_allowed=False,
        paper_order_created=False,
        paper_order_submitted=False,
        paper_order_execution_enabled=False,
        adapter_routing_enabled=False,
        live_order_executed=False,
        safety_notes="Dry-run intent artifact only. It must not be submitted to a paper router, venue adapter, shadow engine, or live exchange.",
    )


def _candidate_blockers(summary: Dict[str, Any], intents: List[PaperDryRunOrderIntent]) -> List[str]:
    blockers: List[str] = []
    if not intents:
        blockers.append("NO_DRY_RUN_INTENTS_CREATED")
    keys = [intent.idempotency_key for intent in intents]
    if len(keys) != len(set(keys)):
        blockers.append("DUPLICATE_IDEMPOTENCY_KEY")
    if str(summary.get("replay_status", "")) == "PAPER_REPLAY_WATCHLIST":
        blockers.append("SOURCE_REPLAY_WATCHLIST_REVIEW_REQUIRED")
    if int(summary.get("simulated_trade_count", 0)) <= 0:
        blockers.append("SOURCE_REPLAY_HAS_NO_SIMULATED_TRADES")
    return blockers


def _candidate_status(summary: Dict[str, Any], blockers: List[str]) -> str:
    if not blockers and str(summary.get("replay_status", "")) == "PAPER_REPLAY_REVIEW_ONLY":
        return "PAPER_EXECUTION_DRY_RUN_REVIEW_ONLY"
    if any(blocker == "NO_DRY_RUN_INTENTS_CREATED" for blocker in blockers):
        return "PAPER_EXECUTION_DRY_RUN_BLOCKED"
    return "PAPER_EXECUTION_DRY_RUN_WATCHLIST"


def _build_for_summary(summary: Dict[str, Any], events: List[Dict[str, Any]]) -> tuple[List[PaperDryRunOrderIntent], PaperExecutionDryRunCandidateSummary]:
    observation_id = str(summary.get("observation_id", ""))
    source_events = [event for event in events if str(event.get("observation_id", "")) == observation_id]
    source_events = source_events[:MAX_DRY_RUN_INTENTS_PER_CANDIDATE]
    intents = [_build_intent(event, summary) for event in source_events]
    blockers = _candidate_blockers(summary, intents)
    status = _candidate_status(summary, blockers)
    unique_count = len({intent.idempotency_key for intent in intents})
    candidate_summary = PaperExecutionDryRunCandidateSummary(
        observation_id=observation_id,
        registry_id=str(summary.get("registry_id", "")),
        comparison_group=str(summary.get("comparison_group", "")),
        timeframe=str(summary.get("timeframe", "")),
        side=str(summary.get("side", "")),
        rr=float(summary.get("rr", 0.0)),
        permission_mode=str(summary.get("permission_mode", "")),
        source_replay_status=str(summary.get("replay_status", "")),
        source_simulated_trade_count=int(summary.get("simulated_trade_count", 0)),
        dry_run_intent_count=len(intents),
        unique_idempotency_key_count=unique_count,
        duplicate_idempotency_key_count=max(0, len(intents) - unique_count),
        dry_run_bridge_status=status,
        blockers=blockers,
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        promotion_allowed=False,
        live_trading_allowed=False,
    )
    return intents, candidate_summary


def _blocker_summary(summaries: List[PaperExecutionDryRunCandidateSummary]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for summary in summaries:
        if not summary.blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in summary.blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step211PaperExecutionDryRunBridgeResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step211PaperExecutionDryRunBridgeResult) -> str:
    lines = [
        "# Step211 v5 Paper Execution Dry-Run Bridge",
        "",
        "Step211 converts Step210 replay evidence into dry-run Paper OrderIntent artifacts.",
        "It does not submit orders, route to adapters, simulate lifecycle fills, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_replay_summary_count: {result.source_replay_summary_count}",
        f"- eligible_replay_summary_count: {result.eligible_replay_summary_count}",
        f"- dry_run_intent_count: {result.dry_run_intent_count}",
        f"- ready_candidate_summary_count: {result.ready_candidate_summary_count}",
        f"- watchlist_candidate_summary_count: {result.watchlist_candidate_summary_count}",
        f"- blocked_candidate_summary_count: {result.blocked_candidate_summary_count}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- shadow_execution_enabled: {result.shadow_execution_enabled}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Candidate summaries",
    ]
    for summary in result.summaries:
        blockers = ", ".join(summary.get("blockers", [])) if summary.get("blockers") else "NO_BLOCKER"
        lines.append(
            "- `{group}` {side} {tf} RR {rr}: status={status}, dry_run_intents={count}, blockers={blockers}".format(
                group=summary.get("comparison_group", ""),
                side=summary.get("side", ""),
                tf=summary.get("timeframe", ""),
                rr=summary.get("rr", 0.0),
                status=summary.get("dry_run_bridge_status", ""),
                count=summary.get("dry_run_intent_count", 0),
                blockers=blockers,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step211 creates dry-run order-intent artifacts only.",
            "- No paper order is submitted.",
            "- VenueRouter, ExchangeAdapter, ShadowExecutionEngine, Telegram, and external APIs are not called.",
            "- `promotion_allowed` remains false for every candidate.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_execution_dry_run_bridge(root: str | Path, *, write_output: bool = True) -> Step211PaperExecutionDryRunBridgeResult:
    root_path = Path(root).resolve()
    step210_path = root_path / "storage/latest/step210_paper_signal_replay_latest.json"
    step210 = _ensure_step210(root_path)
    replay_summaries = list(step210.get("summaries", []) or [])
    replay_events = _load_step210_events(step210)
    eligible_summaries = [summary for summary in replay_summaries if _eligible_summary(summary)]

    all_intents: List[PaperDryRunOrderIntent] = []
    candidate_summaries: List[PaperExecutionDryRunCandidateSummary] = []
    for summary in eligible_summaries:
        intents, candidate_summary = _build_for_summary(summary, replay_events)
        all_intents.extend(intents)
        candidate_summaries.append(candidate_summary)

    dry_run_intents_path = root_path / "data/reports/step211_paper_execution_dry_run_intents.json"
    dry_run_summary_json_path = root_path / "data/reports/step211_paper_execution_dry_run_summary.json"
    dry_run_summary_csv_path = root_path / "data/reports/step211_paper_execution_dry_run_summary.csv"
    markdown_report_path = root_path / "data/reports/step211_paper_execution_dry_run_report.md"
    latest_result_path = root_path / "storage/latest/step211_paper_execution_dry_run_bridge_latest.json"

    intent_dicts = [intent.to_dict() for intent in all_intents]
    summary_dicts = [summary.to_dict() for summary in candidate_summaries]

    result = Step211PaperExecutionDryRunBridgeResult(
        status=STEP211_STATUS_OK,
        root=str(root_path),
        source_step210_result_path=str(step210_path),
        dry_run_intents_path=str(dry_run_intents_path),
        dry_run_summary_json_path=str(dry_run_summary_json_path),
        dry_run_summary_csv_path=str(dry_run_summary_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_replay_summary_count=len(replay_summaries),
        source_replay_event_count=len(replay_events),
        eligible_replay_summary_count=len(eligible_summaries),
        dry_run_intent_count=len(all_intents),
        candidate_summary_count=len(candidate_summaries),
        ready_candidate_summary_count=sum(1 for summary in candidate_summaries if summary.dry_run_bridge_status == "PAPER_EXECUTION_DRY_RUN_REVIEW_ONLY"),
        watchlist_candidate_summary_count=sum(1 for summary in candidate_summaries if summary.dry_run_bridge_status == "PAPER_EXECUTION_DRY_RUN_WATCHLIST"),
        blocked_candidate_summary_count=sum(1 for summary in candidate_summaries if summary.dry_run_bridge_status == "PAPER_EXECUTION_DRY_RUN_BLOCKED"),
        paper_execution_dry_run_bridge_created=True,
        paper_order_intent_dry_run_created=bool(all_intents),
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        order_lifecycle_simulation_enabled=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        summaries=summary_dicts,
        sample_dry_run_order_intents=intent_dicts[:100],
        blocker_summary=_blocker_summary(candidate_summaries),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(dry_run_intents_path, {"dry_run_order_intents": intent_dicts})
        _write_json(dry_run_summary_json_path, {"summaries": summary_dicts})
        _write_csv(dry_run_summary_csv_path, summary_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_execution_dry_run_bridge(root: str | Path) -> Step211ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step211_paper_execution_dry_run_bridge_latest.json"
    if not result_path.exists():
        execute_paper_execution_dry_run_bridge(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))

    intents_path = Path(payload.get("dry_run_intents_path", ""))
    intents: List[Dict[str, Any]] = []
    if intents_path.exists():
        intents = list(_load_json(intents_path).get("dry_run_order_intents", []) or [])
    keys = [str(intent.get("idempotency_key", "")) for intent in intents]

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step210_present": Path(payload.get("source_step210_result_path", "")).exists(),
        "dry_run_intents_json_exists": intents_path.exists(),
        "dry_run_summary_json_exists": Path(payload.get("dry_run_summary_json_path", "")).exists(),
        "dry_run_summary_csv_exists": Path(payload.get("dry_run_summary_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "has_eligible_replay_summaries": int(payload.get("eligible_replay_summary_count", 0)) > 0,
        "dry_run_intents_present": int(payload.get("dry_run_intent_count", 0)) > 0 and bool(intents),
        "idempotency_keys_unique": bool(keys) and len(keys) == len(set(keys)),
        "dry_run_bridge_created": payload.get("paper_execution_dry_run_bridge_created") is True,
        "canonical_order_id_chain_complete": bool(intents) and all(chain_complete(intent, through="order_intent") for intent in intents),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(intent.get("execution_allowed") is False for intent in intents)
        and all(intent.get("paper_order_created") is False for intent in intents)
        and all(intent.get("paper_order_submitted") is False for intent in intents),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False
        and all(intent.get("adapter_routing_enabled") is False for intent in intents),
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False,
        "no_order_lifecycle_simulation": payload.get("order_lifecycle_simulation_enabled") is False,
        "no_auto_promotion": payload.get("auto_strategy_promotion") is False
        and all(summary.get("promotion_allowed") is False for summary in payload.get("summaries", [])),
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(intent.get("live_order_executed") is False for intent in intents),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step211ValidationResult(
        status=STEP211_VALIDATION_OK if not failures else "STEP211_V5_PAPER_EXECUTION_DRY_RUN_BRIDGE_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
