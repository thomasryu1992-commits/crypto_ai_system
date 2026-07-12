from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from crypto_ai_system.execution.simulated_paper_order_lifecycle import (
    execute_simulated_paper_order_lifecycle,
)
from crypto_ai_system.utils.audit import utc_now_canonical
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    chain_complete,
    execution_id_from_order_intent,
    feedback_cycle_id_from_outcome,
    missing_chain_fields,
    outcome_id_from_reconciliation,
    reconciliation_id_from_execution,
)

STEP213_STATUS_OK = "STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_OK"
STEP213_ID_CHAIN_VERSION = ORDER_ID_CHAIN_VERSION
STEP213_RECONCILIATION_EVIDENCE_VERSION = "step272_paper_reconciliation_evidence_v1"
STEP213_VALIDATION_OK = "STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_VALIDATION_OK"

MIN_REVIEW_OUTCOMES = 3
MIN_EXPECTANCY_R = 0.0
MIN_LIFECYCLE_QUALITY_SCORE = 0.95


@dataclass
class PaperLifecycleOutcomeRecord:
    outcome_id: str
    source_step: str
    dry_run_order_intent_id: str
    idempotency_key: str
    simulated_order_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    quantity: float
    entry_price: float
    final_lifecycle_status: str
    lifecycle_event_count: int
    simulated_close_r: float
    simulated_close_reason: str
    outcome_label: str
    lifecycle_quality_score: float
    full_sequence_observed: bool
    rejected: bool
    adapter_called: bool
    real_exchange_order_id: str
    paper_order_submitted: bool
    paper_order_execution_enabled: bool
    live_order_executed: bool
    stored_at_utc: str
    evidence_version: str
    decision_id: str = ""
    risk_gate_id: str = ""
    order_intent_id: str = ""
    execution_id: str = ""
    reconciliation_id: str = ""
    feedback_cycle_id: str = ""
    order_id_chain_version: str = STEP213_ID_CHAIN_VERSION
    order_id_chain_complete: bool = False
    missing_order_id_chain_fields: List[str] = field(default_factory=list)
    expected_order_intent: Dict[str, Any] = field(default_factory=dict)
    simulated_execution: Dict[str, Any] = field(default_factory=dict)
    simulated_fill: Dict[str, Any] = field(default_factory=dict)
    position_delta: Dict[str, Any] = field(default_factory=dict)
    fee_model: Dict[str, Any] = field(default_factory=dict)
    slippage_model: Dict[str, Any] = field(default_factory=dict)
    reconciliation_status: str = ""
    reconciliation_mismatch: bool = False
    mismatch_reasons: List[str] = field(default_factory=list)
    reconciliation_evidence_hash: str = ""
    reconciliation_evidence_version: str = STEP213_RECONCILIATION_EVIDENCE_VERSION
    reconciliation_evidence_complete: bool = False
    reconciliation_evidence_hash_valid: bool = False
    research_signal_id: str = ""
    profile_id: str = ""
    market_regime: str = "unknown"
    timeframe: str = "unknown"
    risk_level: str = "normal"
    data_quality: str = "unknown"
    expectancy: float = 0.0
    win_loss_ratio: float = 0.0
    average_r: float = 0.0
    max_drawdown: float = 0.0
    slippage_bps: float = 0.0
    fill_latency_ms: float = 0.0
    order_rejection_rate: float = 0.0
    stale_data_rate: float = 0.0
    signal_to_outcome_drift: float = 0.0
    paper_live_gap: str | None = "not_applicable"
    api_error_rate: float = 0.0
    manual_override_count: int = 0
    reconciliation_mismatch_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperLifecycleOutcomeCandidateAggregate:
    aggregate_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    outcome_count: int
    closed_count: int
    rejected_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    average_lifecycle_quality_score: float
    min_lifecycle_quality_score: float
    outcome_store_status: str
    blockers: List[str]
    feedback_ready: bool
    promotion_allowed: bool
    paper_order_execution_enabled: bool
    live_trading_allowed: bool
    expectancy: float = 0.0
    win_loss_ratio: float = 0.0
    average_r: float = 0.0
    max_drawdown: float = 0.0
    slippage_bps: float = 0.0
    fill_latency_ms: float = 0.0
    order_rejection_rate: float = 0.0
    stale_data_rate: float = 0.0
    signal_to_outcome_drift: float = 0.0
    paper_live_gap: str | None = "not_applicable"
    api_error_rate: float = 0.0
    manual_override_count: int = 0
    reconciliation_mismatch_count: int = 0
    reconciliation_matched_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step213PaperLifecycleOutcomeStoreResult:
    status: str
    root: str
    source_step212_result_path: str
    outcome_records_json_path: str
    outcome_records_jsonl_path: str
    candidate_aggregate_json_path: str
    candidate_aggregate_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_lifecycle_summary_count: int
    outcome_record_count: int
    candidate_aggregate_count: int
    feedback_ready_candidate_count: int
    watchlist_candidate_count: int
    blocked_candidate_count: int
    outcome_store_created: bool
    outcome_evidence_store_enabled: bool
    feedback_engine_input_ready: bool
    paper_order_execution_enabled: bool
    paper_trade_execution_enabled: bool
    adapter_routing_enabled: bool
    shadow_execution_enabled: bool
    auto_strategy_promotion: bool
    external_api_call_performed: bool
    live_order_executed: bool
    real_adapter_call_performed: bool
    telegram_real_send: bool
    production_cutover_executable: bool
    live_mode_enable_allowed: bool
    aggregates: List[Dict[str, Any]]
    sample_outcome_records: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=utc_now_canonical)
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step213ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step212_present: bool
    outcome_records_json_exists: bool
    outcome_records_jsonl_exists: bool
    candidate_aggregate_json_exists: bool
    candidate_aggregate_csv_exists: bool
    markdown_report_exists: bool
    source_lifecycle_summaries_present: bool
    outcome_records_present: bool
    candidate_aggregates_present: bool
    outcome_store_created: bool
    feedback_input_ready: bool
    canonical_order_id_chain_complete: bool
    reconciliation_evidence_complete: bool
    reconciliation_evidence_hash_valid: bool
    no_reconciliation_mismatch: bool
    no_paper_order_execution: bool
    no_adapter_routing: bool
    no_shadow_execution: bool
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


def _evidence_hash_payload_from_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "reconciliation_evidence_version": summary.get("reconciliation_evidence_version"),
        "reconciliation_id": summary.get("reconciliation_id"),
        "order_intent_id": summary.get("order_intent_id"),
        "execution_id": summary.get("execution_id"),
        "expected_order_intent": summary.get("expected_order_intent"),
        "simulated_execution": summary.get("simulated_execution"),
        "simulated_fill": summary.get("simulated_fill"),
        "position_delta": summary.get("position_delta"),
        "fee_model": summary.get("fee_model"),
        "slippage_model": summary.get("slippage_model"),
        "reconciliation_status": summary.get("reconciliation_status"),
        "reconciliation_mismatch": summary.get("reconciliation_mismatch"),
        "mismatch_reasons": summary.get("mismatch_reasons"),
    }


def _evidence_hash_valid(summary: Dict[str, Any]) -> bool:
    expected = str(summary.get("reconciliation_evidence_hash", ""))
    actual = _sha256_text(_canonical_json(_evidence_hash_payload_from_summary(summary)))
    return bool(expected) and expected == actual


def _evidence_complete(summary: Dict[str, Any]) -> bool:
    required_fields = (
        "expected_order_intent",
        "simulated_execution",
        "simulated_fill",
        "position_delta",
        "fee_model",
        "slippage_model",
        "reconciliation_status",
        "reconciliation_mismatch",
        "mismatch_reasons",
        "reconciliation_evidence_hash",
        "reconciliation_evidence_version",
    )
    return all(field in summary and summary.get(field) not in (None, "") for field in required_fields)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["aggregate_id", "outcome_store_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key, value in list(out.items()):
                if isinstance(value, (dict, list)):
                    out[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)
            out["blockers"] = "|".join(row.get("blockers", []))
            writer.writerow(out)


def _ensure_step212(root: Path, *, allow_regeneration: bool = False) -> Dict[str, Any]:
    path = root / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json"
    if not path.exists():
        if allow_regeneration:
            execute_simulated_paper_order_lifecycle(root, write_output=True)
        else:
            raise FileNotFoundError(
                f"Missing required Step212 source artifact: {path}. Step268 outcome store fails closed; "
                "run explicit regeneration command before outcome generation."
            )
    return _load_json(path)


def _load_step212_summaries(step212: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary_path = Path(step212.get("lifecycle_summary_json_path", ""))
    if summary_path.exists():
        return list(_load_json(summary_path).get("summaries", []) or [])
    return list(step212.get("summaries", []) or [])


def _outcome_label(summary: Dict[str, Any]) -> str:
    status = str(summary.get("final_lifecycle_status", ""))
    close_r = float(summary.get("simulated_close_r", 0.0))
    if status == "SIMULATED_REJECTED":
        return "REJECTED"
    if close_r > 0:
        return "WIN"
    if close_r < 0:
        return "LOSS"
    return "BREAKEVEN"


def _quality_score(summary: Dict[str, Any]) -> float:
    if str(summary.get("final_lifecycle_status", "")) == "SIMULATED_REJECTED":
        return 0.0
    event_count = int(summary.get("lifecycle_event_count", 0))
    if event_count >= 4:
        return 1.0
    if event_count <= 0:
        return 0.0
    return max(0.0, min(1.0, event_count / 4.0))


def _full_sequence_observed(summary: Dict[str, Any]) -> bool:
    return str(summary.get("final_lifecycle_status", "")) == "SIMULATED_CLOSED" and int(summary.get("lifecycle_event_count", 0)) >= 4


def _record_id(summary: Dict[str, Any]) -> str:
    order_intent_id = str(summary.get("order_intent_id") or summary.get("dry_run_order_intent_id", ""))
    execution_id = str(summary.get("execution_id") or "")
    if not execution_id:
        execution_id = execution_id_from_order_intent(order_intent_id, str(summary.get("idempotency_key", "")), str(summary.get("simulated_order_id", "")))
    reconciliation_id = str(summary.get("reconciliation_id") or reconciliation_id_from_execution(order_intent_id, execution_id))
    return outcome_id_from_reconciliation(reconciliation_id, summary.get("simulated_close_r", ""), summary.get("simulated_close_reason", ""))


def _build_outcome_record(summary: Dict[str, Any]) -> PaperLifecycleOutcomeRecord:
    label = _outcome_label(summary)
    quality = _quality_score(summary)
    order_intent_id = str(summary.get("order_intent_id") or summary.get("dry_run_order_intent_id", ""))
    execution_id = str(summary.get("execution_id") or "")
    if not execution_id:
        execution_id = execution_id_from_order_intent(order_intent_id, str(summary.get("idempotency_key", "")), str(summary.get("simulated_order_id", "")))
    reconciliation_id = str(summary.get("reconciliation_id") or reconciliation_id_from_execution(order_intent_id, execution_id))
    decision_id = str(summary.get("decision_id") or summary.get("source_decision_id") or "")
    risk_gate_id = str(summary.get("risk_gate_id") or "")
    outcome_id = _record_id(summary)
    feedback_cycle_id = feedback_cycle_id_from_outcome(outcome_id, str(summary.get("profile_id", "")), str(summary.get("research_signal_id", "")))
    chain_payload = {
        "research_signal_id": str(summary.get("research_signal_id", "")),
        "decision_id": decision_id,
        "risk_gate_id": risk_gate_id,
        "order_intent_id": order_intent_id,
        "execution_id": execution_id,
        "reconciliation_id": reconciliation_id,
        "outcome_id": outcome_id,
        "feedback_cycle_id": feedback_cycle_id,
    }
    return PaperLifecycleOutcomeRecord(
        outcome_id=outcome_id,
        source_step="step212_simulated_paper_order_lifecycle",
        dry_run_order_intent_id=str(summary.get("dry_run_order_intent_id", "")),
        idempotency_key=str(summary.get("idempotency_key", "")),
        simulated_order_id=str(summary.get("simulated_order_id", "")),
        observation_id=str(summary.get("observation_id", "")),
        registry_id=str(summary.get("registry_id", "")),
        comparison_group=str(summary.get("comparison_group", "")),
        side=str(summary.get("side", "")),
        quantity=float(summary.get("quantity", 0.0)),
        entry_price=float(summary.get("entry_price", 0.0)),
        final_lifecycle_status=str(summary.get("final_lifecycle_status", "")),
        lifecycle_event_count=int(summary.get("lifecycle_event_count", 0)),
        simulated_close_r=float(summary.get("simulated_close_r", 0.0)),
        simulated_close_reason=str(summary.get("simulated_close_reason", "")),
        outcome_label=label,
        lifecycle_quality_score=quality,
        full_sequence_observed=_full_sequence_observed(summary),
        rejected=label == "REJECTED",
        adapter_called=bool(summary.get("adapter_called", False)),
        real_exchange_order_id=str(summary.get("real_exchange_order_id", "")),
        paper_order_submitted=bool(summary.get("paper_order_submitted", False)),
        paper_order_execution_enabled=bool(summary.get("paper_order_execution_enabled", False)),
        live_order_executed=bool(summary.get("live_order_executed", False)),
        stored_at_utc=_utc_now(),
        evidence_version="step271_canonical_id_chain_paper_lifecycle_outcome_store",
        decision_id=decision_id,
        risk_gate_id=risk_gate_id,
        order_intent_id=order_intent_id,
        execution_id=execution_id,
        reconciliation_id=reconciliation_id,
        feedback_cycle_id=feedback_cycle_id,
        order_id_chain_version=STEP213_ID_CHAIN_VERSION,
        order_id_chain_complete=chain_complete(chain_payload, through="outcome"),
        missing_order_id_chain_fields=missing_chain_fields(chain_payload, through="outcome"),
        expected_order_intent=dict(summary.get("expected_order_intent", {}) or {}),
        simulated_execution=dict(summary.get("simulated_execution", {}) or {}),
        simulated_fill=dict(summary.get("simulated_fill", {}) or {}),
        position_delta=dict(summary.get("position_delta", {}) or {}),
        fee_model=dict(summary.get("fee_model", {}) or {}),
        slippage_model=dict(summary.get("slippage_model", {}) or {}),
        reconciliation_status=str(summary.get("reconciliation_status", "")),
        reconciliation_mismatch=bool(summary.get("reconciliation_mismatch", False)),
        mismatch_reasons=list(summary.get("mismatch_reasons", []) or []),
        reconciliation_evidence_hash=str(summary.get("reconciliation_evidence_hash", "")),
        reconciliation_evidence_version=str(summary.get("reconciliation_evidence_version", STEP213_RECONCILIATION_EVIDENCE_VERSION)),
        reconciliation_evidence_complete=_evidence_complete(summary),
        reconciliation_evidence_hash_valid=_evidence_hash_valid(summary),
        research_signal_id=str(summary.get("research_signal_id", "")),
        profile_id=str(summary.get("profile_id", "")),
        market_regime=str(summary.get("market_regime", "unknown")),
        timeframe=str(summary.get("timeframe", "unknown")),
        risk_level=str(summary.get("risk_level", "normal")),
        data_quality=str(summary.get("data_quality", "unknown")),
        expectancy=float(summary.get("simulated_close_r", 0.0)),
        win_loss_ratio=1.0 if label == "WIN" else 0.0,
        average_r=float(summary.get("simulated_close_r", 0.0)),
        max_drawdown=min(0.0, float(summary.get("simulated_close_r", 0.0))),
        slippage_bps=float(summary.get("slippage_bps", summary.get("slippage_model", {}).get("actual_slippage_bps", 0.0) if isinstance(summary.get("slippage_model"), dict) else 0.0)),
        fill_latency_ms=float(summary.get("fill_latency_ms", summary.get("simulated_fill", {}).get("fill_latency_ms", 0.0) if isinstance(summary.get("simulated_fill"), dict) else 0.0)),
        order_rejection_rate=1.0 if label == "REJECTED" else 0.0,
        stale_data_rate=1.0 if summary.get("stale_data") is True else 0.0,
        signal_to_outcome_drift=float(summary.get("signal_to_outcome_drift", 0.0)),
        paper_live_gap="not_applicable",
        api_error_rate=float(summary.get("api_error_rate", 0.0)),
        manual_override_count=int(summary.get("manual_override_count", 0)),
        reconciliation_mismatch_count=1 if bool(summary.get("reconciliation_mismatch", False)) else 0,
    )


def _profit_factor(r_values: List[float]) -> float:
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        return float(gross_profit / gross_loss)
    return 999.0 if gross_profit > 0 else 0.0


def _aggregate_blockers(records: List[PaperLifecycleOutcomeRecord]) -> List[str]:
    blockers: List[str] = []
    if not records:
        return ["NO_OUTCOME_RECORDS"]
    if len(records) < MIN_REVIEW_OUTCOMES:
        blockers.append("OUTCOME_SAMPLE_TOO_LOW")
    if any(not r.order_id_chain_complete for r in records):
        blockers.append("ORDER_ID_CHAIN_INCOMPLETE")
    if any(not r.reconciliation_evidence_complete for r in records):
        blockers.append("RECONCILIATION_EVIDENCE_INCOMPLETE")
    if any(not r.reconciliation_evidence_hash_valid for r in records):
        blockers.append("RECONCILIATION_EVIDENCE_HASH_INVALID")
    if any(r.reconciliation_mismatch for r in records):
        blockers.append("RECONCILIATION_MISMATCH_PRESENT")
    closed = [r for r in records if r.outcome_label != "REJECTED"]
    rejected = [r for r in records if r.outcome_label == "REJECTED"]
    if not closed:
        blockers.append("NO_CLOSED_SIMULATED_OUTCOMES")
    if rejected:
        blockers.append("REJECTED_SIMULATED_OUTCOMES_PRESENT")
    r_values = [r.simulated_close_r for r in closed]
    expectancy = sum(r_values) / len(r_values) if r_values else 0.0
    if expectancy < MIN_EXPECTANCY_R:
        blockers.append("OUTCOME_EXPECTANCY_BELOW_ZERO")
    min_quality = min((r.lifecycle_quality_score for r in records), default=0.0)
    if min_quality < MIN_LIFECYCLE_QUALITY_SCORE:
        blockers.append("LIFECYCLE_QUALITY_BELOW_THRESHOLD")
    return blockers


def _aggregate_status(blockers: List[str], records: List[PaperLifecycleOutcomeRecord]) -> str:
    if not records or "NO_CLOSED_SIMULATED_OUTCOMES" in blockers:
        return "PAPER_OUTCOME_BLOCKED"
    hard = {
        "REJECTED_SIMULATED_OUTCOMES_PRESENT",
        "OUTCOME_EXPECTANCY_BELOW_ZERO",
        "LIFECYCLE_QUALITY_BELOW_THRESHOLD",
        "RECONCILIATION_EVIDENCE_INCOMPLETE",
        "RECONCILIATION_EVIDENCE_HASH_INVALID",
        "RECONCILIATION_MISMATCH_PRESENT",
    }
    if any(b in hard for b in blockers):
        return "PAPER_OUTCOME_BLOCKED"
    if blockers:
        return "PAPER_OUTCOME_WATCHLIST"
    return "PAPER_OUTCOME_REVIEW_ONLY"


def _aggregate_records(records: List[PaperLifecycleOutcomeRecord]) -> PaperLifecycleOutcomeCandidateAggregate:
    first = records[0]
    closed = [r for r in records if r.outcome_label != "REJECTED"]
    rejected = [r for r in records if r.outcome_label == "REJECTED"]
    wins = [r for r in closed if r.outcome_label == "WIN"]
    losses = [r for r in closed if r.outcome_label == "LOSS"]
    breakeven = [r for r in closed if r.outcome_label == "BREAKEVEN"]
    r_values = [r.simulated_close_r for r in closed]
    expectancy = sum(r_values) / len(r_values) if r_values else 0.0
    quality_values = [r.lifecycle_quality_score for r in records]
    blockers = _aggregate_blockers(records)
    status = _aggregate_status(blockers, records)
    aggregate_raw = f"{first.observation_id}|{first.registry_id}|{first.comparison_group}|{len(records)}"
    return PaperLifecycleOutcomeCandidateAggregate(
        aggregate_id="agg_" + hashlib.sha1(aggregate_raw.encode("utf-8")).hexdigest()[:20],
        observation_id=first.observation_id,
        registry_id=first.registry_id,
        comparison_group=first.comparison_group,
        side=first.side,
        outcome_count=len(records),
        closed_count=len(closed),
        rejected_count=len(rejected),
        win_count=len(wins),
        loss_count=len(losses),
        breakeven_count=len(breakeven),
        win_rate=(len(wins) / len(closed)) if closed else 0.0,
        expectancy_r=float(expectancy),
        profit_factor=_profit_factor(r_values),
        average_lifecycle_quality_score=(sum(quality_values) / len(quality_values)) if quality_values else 0.0,
        min_lifecycle_quality_score=min(quality_values) if quality_values else 0.0,
        outcome_store_status=status,
        blockers=blockers,
        feedback_ready=status in {"PAPER_OUTCOME_REVIEW_ONLY", "PAPER_OUTCOME_WATCHLIST"},
        promotion_allowed=False,
        paper_order_execution_enabled=False,
        live_trading_allowed=False,
        expectancy=float(expectancy),
        win_loss_ratio=(len(wins) / len(losses)) if losses else (999.0 if wins else 0.0),
        average_r=float(expectancy),
        max_drawdown=min(0.0, min(r_values) if r_values else 0.0),
        slippage_bps=sum(r.slippage_bps for r in records) / len(records) if records else 0.0,
        fill_latency_ms=sum(r.fill_latency_ms for r in records) / len(records) if records else 0.0,
        order_rejection_rate=len(rejected) / len(records) if records else 0.0,
        stale_data_rate=sum(r.stale_data_rate for r in records) / len(records) if records else 0.0,
        signal_to_outcome_drift=sum(r.signal_to_outcome_drift for r in records) / len(records) if records else 0.0,
        paper_live_gap="not_applicable",
        api_error_rate=sum(r.api_error_rate for r in records) / len(records) if records else 0.0,
        manual_override_count=sum(r.manual_override_count for r in records),
        reconciliation_mismatch_count=sum(1 for r in records if r.reconciliation_mismatch),
        reconciliation_matched_count=sum(1 for r in records if r.reconciliation_status == "RECONCILIATION_MATCHED"),
    )


def _group_records(records: List[PaperLifecycleOutcomeRecord]) -> Dict[str, List[PaperLifecycleOutcomeRecord]]:
    grouped: Dict[str, List[PaperLifecycleOutcomeRecord]] = {}
    for record in records:
        grouped.setdefault(record.observation_id or record.registry_id or record.comparison_group, []).append(record)
    return grouped


def _blocker_summary(aggregates: List[PaperLifecycleOutcomeCandidateAggregate]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for aggregate in aggregates:
        if not aggregate.blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in aggregate.blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step213PaperLifecycleOutcomeStoreResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step213PaperLifecycleOutcomeStoreResult) -> str:
    lines = [
        "# Step213 v5 Paper Lifecycle Outcome Store",
        "",
        "Step213 normalizes Step212 simulated lifecycle summaries into paper outcome evidence records.",
        "It prepares feedback-engine input only and does not execute orders, call adapters, send Telegram messages, or promote strategies.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_lifecycle_summary_count: {result.source_lifecycle_summary_count}",
        f"- outcome_record_count: {result.outcome_record_count}",
        f"- candidate_aggregate_count: {result.candidate_aggregate_count}",
        f"- feedback_ready_candidate_count: {result.feedback_ready_candidate_count}",
        f"- watchlist_candidate_count: {result.watchlist_candidate_count}",
        f"- blocked_candidate_count: {result.blocked_candidate_count}",
        f"- outcome_evidence_store_enabled: {result.outcome_evidence_store_enabled}",
        f"- reconciliation_evidence_version: `{STEP213_RECONCILIATION_EVIDENCE_VERSION}`",
        f"- reconciliation_matched_count: {sum(1 for r in result.sample_outcome_records if r.get('reconciliation_status') == 'RECONCILIATION_MATCHED')}",
        f"- reconciliation_mismatch_count: {sum(1 for r in result.sample_outcome_records if r.get('reconciliation_mismatch') is True)}",
        f"- feedback_engine_input_ready: {result.feedback_engine_input_ready}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Candidate aggregates",
    ]
    for aggregate in result.aggregates:
        blockers = ", ".join(aggregate.get("blockers", [])) if aggregate.get("blockers") else "NO_BLOCKER"
        lines.append(
            "- `{group}` {side}: status={status}, outcomes={outcomes}, expectancy={expectancy:.4f}, "
            "pf={pf:.2f}, quality={quality:.2f}, blockers={blockers}".format(
                group=aggregate.get("comparison_group", ""),
                side=aggregate.get("side", ""),
                status=aggregate.get("outcome_store_status", ""),
                outcomes=aggregate.get("outcome_count", 0),
                expectancy=float(aggregate.get("expectancy_r", 0.0)),
                pf=float(aggregate.get("profit_factor", 0.0)),
                quality=float(aggregate.get("average_lifecycle_quality_score", 0.0)),
                blockers=blockers,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step213 creates outcome evidence only.",
            "- Feedback input readiness is not live trading approval.",
            "- Strategy promotion remains disabled.",
            "- No paper order, adapter, live exchange, Telegram, or external API side effect is performed.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_paper_lifecycle_outcome_store(root: str | Path, *, write_output: bool = True, allow_source_regeneration: bool = False) -> Step213PaperLifecycleOutcomeStoreResult:
    root_path = Path(root).resolve()
    step212_path = root_path / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json"
    step212 = _ensure_step212(root_path, allow_regeneration=allow_source_regeneration)
    lifecycle_summaries = _load_step212_summaries(step212)

    records = [_build_outcome_record(summary) for summary in lifecycle_summaries]
    grouped = _group_records(records)
    aggregates = [_aggregate_records(group) for _, group in sorted(grouped.items())]

    record_dicts = [record.to_dict() for record in records]
    aggregate_dicts = [aggregate.to_dict() for aggregate in aggregates]

    outcome_records_json_path = root_path / "data/reports/step213_paper_lifecycle_outcome_records.json"
    outcome_records_jsonl_path = root_path / "data/stores/step213_paper_lifecycle_outcomes.jsonl"
    candidate_aggregate_json_path = root_path / "data/reports/step213_paper_lifecycle_outcome_candidate_aggregates.json"
    candidate_aggregate_csv_path = root_path / "data/reports/step213_paper_lifecycle_outcome_candidate_aggregates.csv"
    markdown_report_path = root_path / "data/reports/step213_paper_lifecycle_outcome_store_report.md"
    latest_result_path = root_path / "storage/latest/step213_paper_lifecycle_outcome_store_latest.json"

    result = Step213PaperLifecycleOutcomeStoreResult(
        status=STEP213_STATUS_OK,
        root=str(root_path),
        source_step212_result_path=str(step212_path),
        outcome_records_json_path=str(outcome_records_json_path),
        outcome_records_jsonl_path=str(outcome_records_jsonl_path),
        candidate_aggregate_json_path=str(candidate_aggregate_json_path),
        candidate_aggregate_csv_path=str(candidate_aggregate_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_lifecycle_summary_count=len(lifecycle_summaries),
        outcome_record_count=len(records),
        candidate_aggregate_count=len(aggregates),
        feedback_ready_candidate_count=sum(1 for agg in aggregates if agg.feedback_ready),
        watchlist_candidate_count=sum(1 for agg in aggregates if agg.outcome_store_status == "PAPER_OUTCOME_WATCHLIST"),
        blocked_candidate_count=sum(1 for agg in aggregates if agg.outcome_store_status == "PAPER_OUTCOME_BLOCKED"),
        outcome_store_created=True,
        outcome_evidence_store_enabled=True,
        feedback_engine_input_ready=bool(records and aggregates),
        paper_order_execution_enabled=False,
        paper_trade_execution_enabled=False,
        adapter_routing_enabled=False,
        shadow_execution_enabled=False,
        auto_strategy_promotion=False,
        external_api_call_performed=False,
        live_order_executed=False,
        real_adapter_call_performed=False,
        telegram_real_send=False,
        production_cutover_executable=False,
        live_mode_enable_allowed=False,
        aggregates=aggregate_dicts,
        sample_outcome_records=record_dicts[:100],
        blocker_summary=_blocker_summary(aggregates),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(outcome_records_json_path, {"outcome_records": record_dicts})
        _write_jsonl(outcome_records_jsonl_path, record_dicts)
        _write_json(candidate_aggregate_json_path, {"aggregates": aggregate_dicts})
        _write_csv(candidate_aggregate_csv_path, aggregate_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def validate_paper_lifecycle_outcome_store(root: str | Path, *, allow_source_regeneration: bool = False) -> Step213ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step213_paper_lifecycle_outcome_store_latest.json"
    if not result_path.exists():
        if allow_source_regeneration:
            execute_paper_lifecycle_outcome_store(root_path, write_output=True, allow_source_regeneration=True)
        else:
            raise FileNotFoundError(
                f"Missing required Step213 result artifact: {result_path}. Step268 validation fails closed; "
                "run explicit outcome generation first."
            )

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))
    outcome_records = list(payload.get("sample_outcome_records", []) or [])
    aggregates = list(payload.get("aggregates", []) or [])

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step212_present": Path(payload.get("source_step212_result_path", "")).exists(),
        "outcome_records_json_exists": Path(payload.get("outcome_records_json_path", "")).exists(),
        "outcome_records_jsonl_exists": Path(payload.get("outcome_records_jsonl_path", "")).exists(),
        "candidate_aggregate_json_exists": Path(payload.get("candidate_aggregate_json_path", "")).exists(),
        "candidate_aggregate_csv_exists": Path(payload.get("candidate_aggregate_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_lifecycle_summaries_present": int(payload.get("source_lifecycle_summary_count", 0)) > 0,
        "outcome_records_present": int(payload.get("outcome_record_count", 0)) > 0 and bool(outcome_records),
        "canonical_order_id_chain_complete": bool(outcome_records) and all(record.get("order_id_chain_complete") is True for record in outcome_records),
        "reconciliation_evidence_complete": bool(outcome_records) and all(record.get("reconciliation_evidence_complete") is True for record in outcome_records),
        "reconciliation_evidence_hash_valid": bool(outcome_records) and all(record.get("reconciliation_evidence_hash_valid") is True for record in outcome_records),
        "no_reconciliation_mismatch": bool(outcome_records) and all(record.get("reconciliation_mismatch") is False for record in outcome_records),
        "candidate_aggregates_present": int(payload.get("candidate_aggregate_count", 0)) > 0 and bool(aggregates),
        "outcome_store_created": payload.get("outcome_store_created") is True and payload.get("outcome_evidence_store_enabled") is True,
        "feedback_input_ready": payload.get("feedback_engine_input_ready") is True,
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(record.get("paper_order_submitted") is False for record in outcome_records)
        and all(record.get("paper_order_execution_enabled") is False for record in outcome_records),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False,
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False,
        "no_auto_promotion": payload.get("auto_strategy_promotion") is False
        and all(aggregate.get("promotion_allowed") is False for aggregate in aggregates),
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(record.get("adapter_called") is False for record in outcome_records)
        and all(record.get("live_order_executed") is False for record in outcome_records),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step213ValidationResult(
        status=STEP213_VALIDATION_OK if not failures else "STEP213_V5_PAPER_LIFECYCLE_OUTCOME_STORE_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
