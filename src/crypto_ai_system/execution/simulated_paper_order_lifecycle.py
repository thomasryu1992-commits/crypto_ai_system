from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from crypto_ai_system.execution.paper_execution_dry_run_bridge import (
    execute_paper_execution_dry_run_bridge,
)
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    execution_id_from_order_intent,
    reconciliation_id_from_execution,
    chain_complete,
)
from crypto_ai_system.utils.audit import utc_now_canonical

STEP212_STATUS_OK = "STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_OK"
STEP212_ID_CHAIN_VERSION = ORDER_ID_CHAIN_VERSION
STEP212_RECONCILIATION_EVIDENCE_VERSION = "step272_paper_reconciliation_evidence_v1"
DEFAULT_REVIEW_ONLY_FEE_BPS = 4.0
DEFAULT_REVIEW_ONLY_SLIPPAGE_TOLERANCE_BPS = 2.0
DEFAULT_SIMULATED_FILL_LATENCY_MS = 0.0
STEP212_VALIDATION_OK = "STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_VALIDATION_OK"

LIFECYCLE_EVENT_SEQUENCE = [
    "SIMULATED_SUBMIT",
    "SIMULATED_ACK",
    "SIMULATED_FILL",
    "SIMULATED_CLOSE",
]


@dataclass
class SimulatedPaperOrderLifecycleEvent:
    lifecycle_event_id: str
    dry_run_order_intent_id: str
    order_intent_id: str
    decision_id: str
    risk_gate_id: str
    research_signal_id: str
    profile_id: str
    execution_id: str
    reconciliation_id: str
    order_id_chain_version: str
    idempotency_key: str
    source_event_id: str
    observation_id: str
    registry_id: str
    comparison_group: str
    event_type: str
    event_status: str
    event_sequence: int
    simulated_order_id: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    r_multiple: float
    event_time_utc: str
    adapter_called: bool
    real_exchange_order_id: str
    paper_order_submitted: bool
    live_order_executed: bool
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SimulatedPaperOrderLifecycleSummary:
    dry_run_order_intent_id: str
    order_intent_id: str
    decision_id: str
    risk_gate_id: str
    research_signal_id: str
    profile_id: str
    execution_id: str
    reconciliation_id: str
    order_id_chain_version: str
    idempotency_key: str
    observation_id: str
    registry_id: str
    comparison_group: str
    side: str
    quantity: float
    entry_price: float
    final_lifecycle_status: str
    lifecycle_event_count: int
    simulated_order_id: str
    simulated_fill_price: float
    simulated_close_r: float
    simulated_close_reason: str
    expected_order_intent: Dict[str, Any]
    simulated_execution: Dict[str, Any]
    simulated_fill: Dict[str, Any]
    position_delta: Dict[str, Any]
    fee_model: Dict[str, Any]
    slippage_model: Dict[str, Any]
    reconciliation_status: str
    reconciliation_mismatch: bool
    mismatch_reasons: List[str]
    reconciliation_evidence_hash: str
    reconciliation_evidence_version: str
    fill_latency_ms: float
    slippage_bps: float
    fee_usd: float
    lifecycle_blockers: List[str]
    adapter_called: bool
    real_exchange_order_id: str
    paper_order_submitted: bool
    paper_order_execution_enabled: bool
    live_order_executed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step212SimulatedPaperOrderLifecycleResult:
    status: str
    root: str
    source_step211_result_path: str
    lifecycle_events_json_path: str
    lifecycle_events_jsonl_path: str
    lifecycle_summary_json_path: str
    lifecycle_summary_csv_path: str
    markdown_report_path: str
    latest_result_path: str
    source_dry_run_intent_count: int
    lifecycle_summary_count: int
    lifecycle_event_count: int
    simulated_submitted_count: int
    simulated_ack_count: int
    simulated_filled_count: int
    simulated_closed_count: int
    simulated_rejected_count: int
    simulated_paper_order_lifecycle_created: bool
    paper_order_lifecycle_simulation_enabled: bool
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
    summaries: List[Dict[str, Any]]
    sample_lifecycle_events: List[Dict[str, Any]]
    blocker_summary: Dict[str, int]
    timestamp_utc: str = field(default_factory=utc_now_canonical)
    result_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Step212ValidationResult:
    status: str
    result_path: str
    result_hash_valid: bool
    source_step211_present: bool
    lifecycle_events_json_exists: bool
    lifecycle_events_jsonl_exists: bool
    lifecycle_summary_json_exists: bool
    lifecycle_summary_csv_exists: bool
    markdown_report_exists: bool
    source_dry_run_intents_present: bool
    lifecycle_events_present: bool
    lifecycle_summaries_present: bool
    lifecycle_simulation_enabled: bool
    canonical_order_id_chain_complete: bool
    reconciliation_evidence_complete: bool
    reconciliation_evidence_hash_valid: bool
    no_reconciliation_mismatch: bool
    event_sequence_valid: bool
    no_duplicate_simulated_order_ids: bool
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
    fieldnames = list(rows[0].keys()) if rows else ["dry_run_order_intent_id", "final_lifecycle_status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key, value in list(out.items()):
                if isinstance(value, (dict, list)):
                    out[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)
            out["lifecycle_blockers"] = "|".join(row.get("lifecycle_blockers", []))
            out["mismatch_reasons"] = "|".join(row.get("mismatch_reasons", []))
            writer.writerow(out)


def _ensure_step211(root: Path) -> Dict[str, Any]:
    path = root / "storage/latest/step211_paper_execution_dry_run_bridge_latest.json"
    if not path.exists():
        execute_paper_execution_dry_run_bridge(root, write_output=True)
    return _load_json(path)


def _load_step211_intents(step211: Dict[str, Any]) -> List[Dict[str, Any]]:
    intent_path = Path(step211.get("dry_run_intents_path", ""))
    if intent_path.exists():
        return list(_load_json(intent_path).get("dry_run_order_intents", []) or [])
    return list(step211.get("sample_dry_run_order_intents", []) or [])


def _simulated_order_id(intent: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            "step212_simulated_order_legacy_alias",
            str(intent.get("order_intent_id") or intent.get("dry_run_order_intent_id", "")),
            str(intent.get("idempotency_key", "")),
            str(intent.get("entry_price", "")),
        ]
    )
    return "spo_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _order_intent_id(intent: Dict[str, Any]) -> str:
    return str(intent.get("order_intent_id") or intent.get("dry_run_order_intent_id") or "")


def _execution_id(intent: Dict[str, Any], simulated_order_id: str) -> str:
    existing = str(intent.get("execution_id") or "").strip()
    if existing:
        return existing
    return execution_id_from_order_intent(_order_intent_id(intent), str(intent.get("idempotency_key", "")), simulated_order_id)


def _intent_is_valid(intent: Dict[str, Any]) -> bool:
    return (
        float(intent.get("quantity", 0.0)) > 0.0
        and float(intent.get("entry_price", 0.0)) > 0.0
        and str(intent.get("dry_run_order_intent_id", ""))
        and str(intent.get("order_intent_id", intent.get("dry_run_order_intent_id", "")))
        and str(intent.get("decision_id", ""))
        and str(intent.get("risk_gate_id", ""))
        and str(intent.get("research_signal_id", ""))
        and str(intent.get("idempotency_key", ""))
    )


def _close_reason_from_r(r_multiple: float, source_exit_reason: str) -> str:
    if source_exit_reason:
        return f"SIMULATED_{source_exit_reason}"
    if r_multiple > 0:
        return "SIMULATED_TAKE_PROFIT"
    if r_multiple < 0:
        return "SIMULATED_STOP_LOSS"
    return "SIMULATED_TIME_EXIT"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round8(value: float) -> float:
    return round(float(value), 8)


def _expected_order_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "order_intent_id": _order_intent_id(intent),
        "dry_run_order_intent_id": str(intent.get("dry_run_order_intent_id", "")),
        "decision_id": str(intent.get("decision_id", "")),
        "risk_gate_id": str(intent.get("risk_gate_id", "")),
        "research_signal_id": str(intent.get("research_signal_id", "")),
        "profile_id": str(intent.get("profile_id", "")),
        "idempotency_key": str(intent.get("idempotency_key", "")),
        "side": str(intent.get("side", "")),
        "order_type": str(intent.get("order_type", "")),
        "quantity": _round8(_safe_float(intent.get("quantity"))),
        "entry_price": _round8(_safe_float(intent.get("entry_price"))),
        "stop_loss": _round8(_safe_float(intent.get("stop_loss"))),
        "take_profit": _round8(_safe_float(intent.get("take_profit"))),
        "dry_run_notional_usd": _round8(_safe_float(intent.get("dry_run_notional_usd"))),
        "source_event_id": str(intent.get("source_event_id", "")),
    }


def _fill_notional(fill_price: float, quantity: float) -> float:
    return _round8(abs(fill_price * quantity))


def _simulated_execution_payload(intent: Dict[str, Any], simulated_order_id: str, execution_id: str, *, valid: bool, event_count: int) -> Dict[str, Any]:
    return {
        "execution_id": execution_id,
        "order_intent_id": _order_intent_id(intent),
        "simulated_order_id": simulated_order_id,
        "execution_status": "SIMULATED_FILLED" if valid else "SIMULATED_REJECTED",
        "event_count": int(event_count),
        "local_simulation_only": True,
        "adapter_called": False,
        "real_exchange_order_id": "",
        "paper_order_submitted": False,
        "live_order_executed": False,
    }


def _simulated_fill_payload(intent: Dict[str, Any], *, valid: bool) -> Dict[str, Any]:
    quantity = _round8(_safe_float(intent.get("quantity"))) if valid else 0.0
    fill_price = _round8(_safe_float(intent.get("entry_price"))) if valid else 0.0
    fill_notional = _fill_notional(fill_price, quantity) if valid else 0.0
    return {
        "fill_status": "FILLED" if valid else "NO_FILL",
        "fill_price": fill_price,
        "fill_quantity": quantity,
        "fill_notional_usd": fill_notional,
        "fill_latency_ms": DEFAULT_SIMULATED_FILL_LATENCY_MS if valid else 0.0,
        "exchange_fill": False,
    }


def _position_delta_payload(intent: Dict[str, Any], fill: Dict[str, Any], source_r: float) -> Dict[str, Any]:
    side = str(intent.get("side", "")).upper()
    quantity = _safe_float(fill.get("fill_quantity"))
    signed_quantity = quantity if side == "LONG" else -quantity if side == "SHORT" else 0.0
    return {
        "side": side,
        "base_quantity_delta": _round8(signed_quantity),
        "absolute_quantity": _round8(abs(quantity)),
        "entry_notional_usd": _round8(_safe_float(fill.get("fill_notional_usd"))),
        "close_r_multiple": _round8(source_r),
        "position_opened": quantity > 0,
        "position_closed_by_simulation": quantity > 0,
    }


def _fee_model_payload(fill: Dict[str, Any]) -> Dict[str, Any]:
    notional = _safe_float(fill.get("fill_notional_usd"))
    fee_usd = _round8(notional * DEFAULT_REVIEW_ONLY_FEE_BPS / 10000.0)
    return {
        "fee_model_version": "step272_static_review_only_fee_model_v1",
        "fee_bps": DEFAULT_REVIEW_ONLY_FEE_BPS,
        "fee_usd": fee_usd,
        "fee_currency": "USD",
        "source": "review_only_static_model",
    }


def _slippage_model_payload(intent: Dict[str, Any], fill: Dict[str, Any]) -> Dict[str, Any]:
    expected_price = _safe_float(intent.get("entry_price"))
    fill_price = _safe_float(fill.get("fill_price"))
    if expected_price > 0 and fill_price > 0:
        actual_slippage_bps = _round8(abs(fill_price - expected_price) / expected_price * 10000.0)
    else:
        actual_slippage_bps = 0.0
    return {
        "slippage_model_version": "step272_static_review_only_slippage_model_v1",
        "expected_fill_price": _round8(expected_price),
        "simulated_fill_price": _round8(fill_price),
        "actual_slippage_bps": actual_slippage_bps,
        "configured_slippage_tolerance_bps": DEFAULT_REVIEW_ONLY_SLIPPAGE_TOLERANCE_BPS,
        "within_tolerance": actual_slippage_bps <= DEFAULT_REVIEW_ONLY_SLIPPAGE_TOLERANCE_BPS,
        "source": "review_only_local_simulation",
    }


def _mismatch_reasons(intent: Dict[str, Any], execution: Dict[str, Any], fill: Dict[str, Any], slippage: Dict[str, Any], *, valid: bool) -> List[str]:
    reasons: List[str] = []
    expected = _expected_order_intent(intent)
    if not valid:
        reasons.append("INVALID_DRY_RUN_INTENT")
    if str(execution.get("order_intent_id", "")) != str(expected.get("order_intent_id", "")):
        reasons.append("ORDER_INTENT_ID_MISMATCH")
    if valid and _round8(_safe_float(fill.get("fill_quantity"))) != _round8(_safe_float(expected.get("quantity"))):
        reasons.append("FILL_QUANTITY_MISMATCH")
    if valid and _round8(_safe_float(fill.get("fill_price"))) != _round8(_safe_float(expected.get("entry_price"))):
        reasons.append("FILL_PRICE_MISMATCH")
    if bool(execution.get("adapter_called", False)):
        reasons.append("ADAPTER_CALLED_DURING_REVIEW_ONLY_SIMULATION")
    if bool(execution.get("paper_order_submitted", False)):
        reasons.append("PAPER_ORDER_SUBMITTED_DURING_REVIEW_ONLY_SIMULATION")
    if bool(execution.get("live_order_executed", False)):
        reasons.append("LIVE_ORDER_EXECUTED_DURING_REVIEW_ONLY_SIMULATION")
    if not bool(slippage.get("within_tolerance", False)):
        reasons.append("SLIPPAGE_TOLERANCE_EXCEEDED")
    return reasons


def _reconciliation_evidence_payload(
    intent: Dict[str, Any],
    simulated_order_id: str,
    execution_id: str,
    reconciliation_id: str,
    *,
    valid: bool,
    event_count: int,
    source_r: float,
) -> Dict[str, Any]:
    expected = _expected_order_intent(intent)
    execution = _simulated_execution_payload(intent, simulated_order_id, execution_id, valid=valid, event_count=event_count)
    fill = _simulated_fill_payload(intent, valid=valid)
    position_delta = _position_delta_payload(intent, fill, source_r if valid else 0.0)
    fee_model = _fee_model_payload(fill)
    slippage_model = _slippage_model_payload(intent, fill)
    mismatch_reasons = _mismatch_reasons(intent, execution, fill, slippage_model, valid=valid)
    mismatch = bool([reason for reason in mismatch_reasons if reason != "INVALID_DRY_RUN_INTENT"])
    if not valid:
        status = "RECONCILIATION_REJECTED_INVALID_INTENT"
    elif mismatch:
        status = "RECONCILIATION_MISMATCH"
    else:
        status = "RECONCILIATION_MATCHED"
    evidence = {
        "reconciliation_evidence_version": STEP212_RECONCILIATION_EVIDENCE_VERSION,
        "reconciliation_id": reconciliation_id,
        "order_intent_id": expected.get("order_intent_id", ""),
        "execution_id": execution_id,
        "expected_order_intent": expected,
        "simulated_execution": execution,
        "simulated_fill": fill,
        "position_delta": position_delta,
        "fee_model": fee_model,
        "slippage_model": slippage_model,
        "reconciliation_status": status,
        "reconciliation_mismatch": mismatch,
        "mismatch_reasons": mismatch_reasons,
    }
    evidence["reconciliation_evidence_hash"] = _sha256_text(_canonical_json({k: v for k, v in evidence.items() if k != "reconciliation_evidence_hash"}))
    return evidence


def _evidence_hash_valid(summary: Dict[str, Any]) -> bool:
    required = {
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
    expected = str(summary.get("reconciliation_evidence_hash", ""))
    actual = _sha256_text(_canonical_json(required))
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


def _base_event_kwargs(intent: Dict[str, Any], simulated_order_id: str, execution_id: str, reconciliation_id: str) -> Dict[str, Any]:
    order_intent_id = _order_intent_id(intent)
    return {
        "dry_run_order_intent_id": str(intent.get("dry_run_order_intent_id", "")),
        "order_intent_id": order_intent_id,
        "decision_id": str(intent.get("decision_id", "")),
        "risk_gate_id": str(intent.get("risk_gate_id", "")),
        "research_signal_id": str(intent.get("research_signal_id", "")),
        "profile_id": str(intent.get("profile_id", "")),
        "execution_id": execution_id,
        "reconciliation_id": reconciliation_id,
        "order_id_chain_version": STEP212_ID_CHAIN_VERSION,
        "idempotency_key": str(intent.get("idempotency_key", "")),
        "source_event_id": str(intent.get("source_event_id", "")),
        "observation_id": str(intent.get("observation_id", "")),
        "registry_id": str(intent.get("registry_id", "")),
        "comparison_group": str(intent.get("comparison_group", "")),
        "simulated_order_id": simulated_order_id,
        "side": str(intent.get("side", "")),
        "quantity": float(intent.get("quantity", 0.0)),
        "entry_price": float(intent.get("entry_price", 0.0)),
        "stop_loss": float(intent.get("stop_loss", 0.0)),
        "take_profit": float(intent.get("take_profit", 0.0)),
        "r_multiple": float(intent.get("source_r_multiple", 0.0)),
        "adapter_called": False,
        "real_exchange_order_id": "",
        "paper_order_submitted": False,
        "live_order_executed": False,
    }


def _event_id(simulated_order_id: str, event_type: str, sequence: int) -> str:
    raw = f"{simulated_order_id}|{event_type}|{sequence}"
    return "loev_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _make_event(intent: Dict[str, Any], simulated_order_id: str, execution_id: str, reconciliation_id: str, event_type: str, event_status: str, sequence: int, details: Dict[str, Any]) -> SimulatedPaperOrderLifecycleEvent:
    base = _base_event_kwargs(intent, simulated_order_id, execution_id, reconciliation_id)
    return SimulatedPaperOrderLifecycleEvent(
        lifecycle_event_id=_event_id(simulated_order_id, event_type, sequence),
        event_type=event_type,
        event_status=event_status,
        event_sequence=sequence,
        event_time_utc=_utc_now(),
        details=details,
        **base,
    )


def _summary_reconciliation_kwargs(
    intent: Dict[str, Any],
    simulated_order_id: str,
    execution_id: str,
    reconciliation_id: str,
    *,
    valid: bool,
    event_count: int,
    source_r: float,
) -> Dict[str, Any]:
    evidence = _reconciliation_evidence_payload(
        intent,
        simulated_order_id,
        execution_id,
        reconciliation_id,
        valid=valid,
        event_count=event_count,
        source_r=source_r,
    )
    return {
        "expected_order_intent": evidence["expected_order_intent"],
        "simulated_execution": evidence["simulated_execution"],
        "simulated_fill": evidence["simulated_fill"],
        "position_delta": evidence["position_delta"],
        "fee_model": evidence["fee_model"],
        "slippage_model": evidence["slippage_model"],
        "reconciliation_status": evidence["reconciliation_status"],
        "reconciliation_mismatch": evidence["reconciliation_mismatch"],
        "mismatch_reasons": evidence["mismatch_reasons"],
        "reconciliation_evidence_hash": evidence["reconciliation_evidence_hash"],
        "reconciliation_evidence_version": evidence["reconciliation_evidence_version"],
        "fill_latency_ms": float(evidence["simulated_fill"].get("fill_latency_ms", 0.0)),
        "slippage_bps": float(evidence["slippage_model"].get("actual_slippage_bps", 0.0)),
        "fee_usd": float(evidence["fee_model"].get("fee_usd", 0.0)),
    }


def _simulate_intent_lifecycle(intent: Dict[str, Any]) -> Tuple[List[SimulatedPaperOrderLifecycleEvent], SimulatedPaperOrderLifecycleSummary]:
    simulated_order_id = _simulated_order_id(intent)
    execution_id = _execution_id(intent, simulated_order_id)
    reconciliation_id = reconciliation_id_from_execution(_order_intent_id(intent), execution_id)
    valid = _intent_is_valid(intent)
    events: List[SimulatedPaperOrderLifecycleEvent] = []

    events.append(
        _make_event(
            intent,
            simulated_order_id,
            execution_id,
            reconciliation_id,
            "SIMULATED_SUBMIT",
            "SUBMIT_ACCEPTED_FOR_SIMULATION" if valid else "SUBMIT_REJECTED_BY_SIMULATION_VALIDATION",
            1,
            {"execution_path": "local_simulation_only", "valid_intent": valid},
        )
    )

    blockers: List[str] = []
    if not valid:
        blockers.append("INVALID_DRY_RUN_INTENT")
        final_status = "SIMULATED_REJECTED"
        close_reason = "SIMULATED_REJECTED_INVALID_INTENT"
        summary = SimulatedPaperOrderLifecycleSummary(
            dry_run_order_intent_id=str(intent.get("dry_run_order_intent_id", "")),
            order_intent_id=_order_intent_id(intent),
            decision_id=str(intent.get("decision_id", "")),
            risk_gate_id=str(intent.get("risk_gate_id", "")),
            research_signal_id=str(intent.get("research_signal_id", "")),
            profile_id=str(intent.get("profile_id", "")),
            execution_id=execution_id,
            reconciliation_id=reconciliation_id,
            order_id_chain_version=STEP212_ID_CHAIN_VERSION,
            idempotency_key=str(intent.get("idempotency_key", "")),
            observation_id=str(intent.get("observation_id", "")),
            registry_id=str(intent.get("registry_id", "")),
            comparison_group=str(intent.get("comparison_group", "")),
            side=str(intent.get("side", "")),
            quantity=float(intent.get("quantity", 0.0)),
            entry_price=float(intent.get("entry_price", 0.0)),
            final_lifecycle_status=final_status,
            lifecycle_event_count=len(events),
            simulated_order_id=simulated_order_id,
            simulated_fill_price=0.0,
            simulated_close_r=0.0,
            simulated_close_reason=close_reason,
            **_summary_reconciliation_kwargs(intent, simulated_order_id, execution_id, reconciliation_id, valid=False, event_count=len(events), source_r=0.0),
            lifecycle_blockers=blockers,
            adapter_called=False,
            real_exchange_order_id="",
            paper_order_submitted=False,
            paper_order_execution_enabled=False,
            live_order_executed=False,
        )
        return events, summary

    source_r = float(intent.get("source_r_multiple", 0.0))
    source_exit_reason = str(intent.get("source_exit_reason", ""))
    close_reason = _close_reason_from_r(source_r, source_exit_reason)

    events.append(
        _make_event(
            intent,
            simulated_order_id,
            execution_id,
            reconciliation_id,
            "SIMULATED_ACK",
            "ACK_SIMULATED",
            2,
            {"ack_source": "local_lifecycle_simulator", "exchange_ack": False},
        )
    )
    events.append(
        _make_event(
            intent,
            simulated_order_id,
            execution_id,
            reconciliation_id,
            "SIMULATED_FILL",
            "FILL_SIMULATED",
            3,
            {"fill_price": float(intent.get("entry_price", 0.0)), "fill_quantity": float(intent.get("quantity", 0.0)), "exchange_fill": False},
        )
    )
    events.append(
        _make_event(
            intent,
            simulated_order_id,
            execution_id,
            reconciliation_id,
            "SIMULATED_CLOSE",
            "CLOSE_SIMULATED",
            4,
            {"close_r_multiple": source_r, "close_reason": close_reason, "exchange_close": False},
        )
    )

    summary = SimulatedPaperOrderLifecycleSummary(
        dry_run_order_intent_id=str(intent.get("dry_run_order_intent_id", "")),
        order_intent_id=_order_intent_id(intent),
        decision_id=str(intent.get("decision_id", "")),
        risk_gate_id=str(intent.get("risk_gate_id", "")),
        research_signal_id=str(intent.get("research_signal_id", "")),
        profile_id=str(intent.get("profile_id", "")),
        execution_id=execution_id,
        reconciliation_id=reconciliation_id,
        order_id_chain_version=STEP212_ID_CHAIN_VERSION,
        idempotency_key=str(intent.get("idempotency_key", "")),
        observation_id=str(intent.get("observation_id", "")),
        registry_id=str(intent.get("registry_id", "")),
        comparison_group=str(intent.get("comparison_group", "")),
        side=str(intent.get("side", "")),
        quantity=float(intent.get("quantity", 0.0)),
        entry_price=float(intent.get("entry_price", 0.0)),
        final_lifecycle_status="SIMULATED_CLOSED",
        lifecycle_event_count=len(events),
        simulated_order_id=simulated_order_id,
        simulated_fill_price=float(intent.get("entry_price", 0.0)),
        simulated_close_r=source_r,
        simulated_close_reason=close_reason,
        **_summary_reconciliation_kwargs(intent, simulated_order_id, execution_id, reconciliation_id, valid=True, event_count=len(events), source_r=source_r),
        lifecycle_blockers=[],
        adapter_called=False,
        real_exchange_order_id="",
        paper_order_submitted=False,
        paper_order_execution_enabled=False,
        live_order_executed=False,
    )
    return events, summary


def _blocker_summary(summaries: List[SimulatedPaperOrderLifecycleSummary]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for summary in summaries:
        if not summary.lifecycle_blockers:
            out["NO_BLOCKER"] = out.get("NO_BLOCKER", 0) + 1
        for blocker in summary.lifecycle_blockers:
            out[blocker] = out.get(blocker, 0) + 1
    return dict(sorted(out.items()))


def _result_hash_payload(result: Step212SimulatedPaperOrderLifecycleResult) -> Dict[str, Any]:
    payload = result.to_dict()
    payload.pop("result_sha256", None)
    return payload


def _render_markdown(result: Step212SimulatedPaperOrderLifecycleResult) -> str:
    lines = [
        "# Step212 v5 Simulated Paper Order Lifecycle",
        "",
        "Step212 simulates paper order lifecycle events from Step211 dry-run Paper OrderIntent artifacts.",
        "It does not submit orders, route to adapters, use ShadowExecutionEngine, send Telegram messages, or enable live trading.",
        "",
        "## Summary",
        f"- status: `{result.status}`",
        f"- source_dry_run_intent_count: {result.source_dry_run_intent_count}",
        f"- lifecycle_event_count: {result.lifecycle_event_count}",
        f"- lifecycle_summary_count: {result.lifecycle_summary_count}",
        f"- simulated_submitted_count: {result.simulated_submitted_count}",
        f"- simulated_ack_count: {result.simulated_ack_count}",
        f"- simulated_filled_count: {result.simulated_filled_count}",
        f"- simulated_closed_count: {result.simulated_closed_count}",
        f"- simulated_rejected_count: {result.simulated_rejected_count}",
        f"- reconciliation_evidence_version: `{STEP212_RECONCILIATION_EVIDENCE_VERSION}`",
        f"- reconciliation_matched_count: {sum(1 for s in result.summaries if s.get('reconciliation_status') == 'RECONCILIATION_MATCHED')}",
        f"- reconciliation_mismatch_count: {sum(1 for s in result.summaries if s.get('reconciliation_mismatch') is True)}",
        f"- paper_order_lifecycle_simulation_enabled: {result.paper_order_lifecycle_simulation_enabled}",
        f"- paper_order_execution_enabled: {result.paper_order_execution_enabled}",
        f"- adapter_routing_enabled: {result.adapter_routing_enabled}",
        f"- shadow_execution_enabled: {result.shadow_execution_enabled}",
        f"- live_order_executed: {result.live_order_executed}",
        "",
        "## Lifecycle summaries",
    ]
    for summary in result.summaries:
        blockers = ", ".join(summary.get("lifecycle_blockers", [])) if summary.get("lifecycle_blockers") else "NO_BLOCKER"
        lines.append(
            "- `{intent}` {side}: final={status}, events={events}, close_r={r:.4f}, blockers={blockers}".format(
                intent=summary.get("dry_run_order_intent_id", ""),
                side=summary.get("side", ""),
                status=summary.get("final_lifecycle_status", ""),
                events=summary.get("lifecycle_event_count", 0),
                r=float(summary.get("simulated_close_r", 0.0)),
                blockers=blockers,
            )
        )
    lines.extend(
        [
            "",
            "## Policy",
            "- Step212 is local lifecycle simulation only.",
            "- No paper order is submitted.",
            "- VenueRouter, ExchangeAdapter, ShadowExecutionEngine, Telegram, and external APIs are not called.",
            "- Live trading remains disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def execute_simulated_paper_order_lifecycle(root: str | Path, *, write_output: bool = True) -> Step212SimulatedPaperOrderLifecycleResult:
    root_path = Path(root).resolve()
    step211_path = root_path / "storage/latest/step211_paper_execution_dry_run_bridge_latest.json"
    step211 = _ensure_step211(root_path)
    intents = _load_step211_intents(step211)

    all_events: List[SimulatedPaperOrderLifecycleEvent] = []
    summaries: List[SimulatedPaperOrderLifecycleSummary] = []
    for intent in intents:
        events, summary = _simulate_intent_lifecycle(intent)
        all_events.extend(events)
        summaries.append(summary)

    event_dicts = [event.to_dict() for event in all_events]
    summary_dicts = [summary.to_dict() for summary in summaries]

    lifecycle_events_json_path = root_path / "data/reports/step212_simulated_paper_order_lifecycle_events.json"
    lifecycle_events_jsonl_path = root_path / "data/events/step212_simulated_paper_order_lifecycle_events.jsonl"
    lifecycle_summary_json_path = root_path / "data/reports/step212_simulated_paper_order_lifecycle_summary.json"
    lifecycle_summary_csv_path = root_path / "data/reports/step212_simulated_paper_order_lifecycle_summary.csv"
    markdown_report_path = root_path / "data/reports/step212_simulated_paper_order_lifecycle_report.md"
    latest_result_path = root_path / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json"

    result = Step212SimulatedPaperOrderLifecycleResult(
        status=STEP212_STATUS_OK,
        root=str(root_path),
        source_step211_result_path=str(step211_path),
        lifecycle_events_json_path=str(lifecycle_events_json_path),
        lifecycle_events_jsonl_path=str(lifecycle_events_jsonl_path),
        lifecycle_summary_json_path=str(lifecycle_summary_json_path),
        lifecycle_summary_csv_path=str(lifecycle_summary_csv_path),
        markdown_report_path=str(markdown_report_path),
        latest_result_path=str(latest_result_path),
        source_dry_run_intent_count=len(intents),
        lifecycle_summary_count=len(summaries),
        lifecycle_event_count=len(all_events),
        simulated_submitted_count=sum(1 for event in all_events if event.event_type == "SIMULATED_SUBMIT"),
        simulated_ack_count=sum(1 for event in all_events if event.event_type == "SIMULATED_ACK"),
        simulated_filled_count=sum(1 for event in all_events if event.event_type == "SIMULATED_FILL"),
        simulated_closed_count=sum(1 for event in all_events if event.event_type == "SIMULATED_CLOSE"),
        simulated_rejected_count=sum(1 for summary in summaries if summary.final_lifecycle_status == "SIMULATED_REJECTED"),
        simulated_paper_order_lifecycle_created=True,
        paper_order_lifecycle_simulation_enabled=True,
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
        summaries=summary_dicts,
        sample_lifecycle_events=event_dicts[:100],
        blocker_summary=_blocker_summary(summaries),
    )
    result.result_sha256 = _sha256_text(_canonical_json(_result_hash_payload(result)))

    if write_output:
        _write_json(lifecycle_events_json_path, {"events": event_dicts})
        _write_jsonl(lifecycle_events_jsonl_path, event_dicts)
        _write_json(lifecycle_summary_json_path, {"summaries": summary_dicts})
        _write_csv(lifecycle_summary_csv_path, summary_dicts)
        markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_report_path.write_text(_render_markdown(result), encoding="utf-8")
        _write_json(latest_result_path, result.to_dict())
    return result


def _event_sequence_valid(events: List[Dict[str, Any]]) -> bool:
    by_order: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        by_order.setdefault(str(event.get("simulated_order_id", "")), []).append(event)
    for grouped in by_order.values():
        sorted_events = sorted(grouped, key=lambda x: int(x.get("event_sequence", 0)))
        types = [str(event.get("event_type", "")) for event in sorted_events]
        if types == ["SIMULATED_SUBMIT"]:
            # Rejected validation path.
            continue
        if types != LIFECYCLE_EVENT_SEQUENCE:
            return False
    return True


def validate_simulated_paper_order_lifecycle(root: str | Path) -> Step212ValidationResult:
    root_path = Path(root).resolve()
    result_path = root_path / "storage/latest/step212_simulated_paper_order_lifecycle_latest.json"
    if not result_path.exists():
        execute_simulated_paper_order_lifecycle(root_path, write_output=True)

    payload = _load_json(result_path)
    expected = payload.get("result_sha256", "")
    actual = _sha256_text(_canonical_json({k: v for k, v in payload.items() if k != "result_sha256"}))

    events_path = Path(payload.get("lifecycle_events_json_path", ""))
    events: List[Dict[str, Any]] = []
    if events_path.exists():
        events = list(_load_json(events_path).get("events", []) or [])
    summaries = list(payload.get("summaries", []) or [])
    simulated_order_ids = [str(summary.get("simulated_order_id", "")) for summary in summaries if str(summary.get("simulated_order_id", ""))]

    checks = {
        "result_hash_valid": bool(expected) and expected == actual,
        "source_step211_present": Path(payload.get("source_step211_result_path", "")).exists(),
        "lifecycle_events_json_exists": events_path.exists(),
        "lifecycle_events_jsonl_exists": Path(payload.get("lifecycle_events_jsonl_path", "")).exists(),
        "lifecycle_summary_json_exists": Path(payload.get("lifecycle_summary_json_path", "")).exists(),
        "lifecycle_summary_csv_exists": Path(payload.get("lifecycle_summary_csv_path", "")).exists(),
        "markdown_report_exists": Path(payload.get("markdown_report_path", "")).exists(),
        "source_dry_run_intents_present": int(payload.get("source_dry_run_intent_count", 0)) > 0,
        "lifecycle_events_present": int(payload.get("lifecycle_event_count", 0)) > 0 and bool(events),
        "lifecycle_summaries_present": int(payload.get("lifecycle_summary_count", 0)) > 0 and bool(summaries),
        "lifecycle_simulation_enabled": payload.get("paper_order_lifecycle_simulation_enabled") is True,
        "canonical_order_id_chain_complete": bool(summaries) and all(chain_complete(summary, through="reconciliation") for summary in summaries),
        "reconciliation_evidence_complete": bool(summaries) and all(_evidence_complete(summary) for summary in summaries),
        "reconciliation_evidence_hash_valid": bool(summaries) and all(_evidence_hash_valid(summary) for summary in summaries),
        "no_reconciliation_mismatch": bool(summaries) and all(summary.get("reconciliation_mismatch") is False for summary in summaries if summary.get("reconciliation_status") != "RECONCILIATION_REJECTED_INVALID_INTENT"),
        "event_sequence_valid": _event_sequence_valid(events),
        "no_duplicate_simulated_order_ids": bool(simulated_order_ids) and len(simulated_order_ids) == len(set(simulated_order_ids)),
        "no_paper_order_execution": payload.get("paper_order_execution_enabled") is False
        and all(event.get("paper_order_submitted") is False for event in events)
        and all(summary.get("paper_order_submitted") is False for summary in summaries)
        and all(summary.get("paper_order_execution_enabled") is False for summary in summaries),
        "no_adapter_routing": payload.get("adapter_routing_enabled") is False,
        "no_shadow_execution": payload.get("shadow_execution_enabled") is False,
        "no_auto_promotion": payload.get("auto_strategy_promotion") is False,
        "no_external_api_calls": payload.get("external_api_call_performed") is False,
        "no_live_side_effects": payload.get("live_order_executed") is False
        and payload.get("real_adapter_call_performed") is False
        and payload.get("telegram_real_send") is False
        and all(event.get("adapter_called") is False for event in events)
        and all(event.get("live_order_executed") is False for event in events)
        and all(summary.get("adapter_called") is False for summary in summaries)
        and all(summary.get("live_order_executed") is False for summary in summaries),
        "no_production_cutover": payload.get("production_cutover_executable") is False
        and payload.get("live_mode_enable_allowed") is False,
    }
    failures = [name for name, ok in checks.items() if not ok]
    return Step212ValidationResult(
        status=STEP212_VALIDATION_OK if not failures else "STEP212_V5_SIMULATED_PAPER_ORDER_LIFECYCLE_VALIDATION_FAILED",
        result_path=str(result_path),
        blocking_failure_count=len(failures),
        blocking_failures=failures,
        **checks,
    )
