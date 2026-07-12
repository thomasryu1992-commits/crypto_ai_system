from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.trading.order_id_chain import (
    ORDER_ID_CHAIN_VERSION,
    chain_complete,
    execution_id_from_order_intent,
    missing_chain_fields,
    order_intent_id_from_payload,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PAPER_EXECUTION_ENGINE_VERSION = "step294_paper_execution_engine_v2"
PAPER_EXECUTION_REGISTRY_NAME = "paper_execution_registry"

STATUS_PAPER_FILLED = "PAPER_FILLED"
STATUS_PAPER_PARTIALLY_FILLED = "PAPER_PARTIALLY_FILLED"
STATUS_PAPER_CANCELLED = "PAPER_CANCELLED"
STATUS_PAPER_REJECTED = "PAPER_REJECTED"
STATUS_PAPER_PENDING_RECONCILIATION = "PAPER_PENDING_RECONCILIATION"

PAPER_LIFECYCLE_STATES = (
    "ORDER_INTENT_CREATED",
    "PAPER_SUBMITTED",
    "PAPER_ACCEPTED",
    "PAPER_PARTIALLY_FILLED",
    "PAPER_FILLED",
    "PAPER_CANCELLED",
    "PAPER_REJECTED",
    "PAPER_CLOSED",
    "PENDING_RECONCILIATION",
)

TERMINAL_STATES = {"PAPER_FILLED", "PAPER_CANCELLED", "PAPER_REJECTED", "PENDING_RECONCILIATION"}

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
ADAPTER_ROUTING_ENABLED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
REAL_EXCHANGE_ORDER_ID = None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _event(event_type: str, sequence: int, state: str, status: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    base = {
        "paper_execution_engine_version": PAPER_EXECUTION_ENGINE_VERSION,
        "event_type": event_type,
        "event_sequence": sequence,
        "state": state,
        "status": status,
        "event_time_utc": utc_now_canonical(),
        "order_intent_id": payload.get("order_intent_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "profile_id": payload.get("profile_id"),
        "adapter_called": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "real_exchange_order_id": REAL_EXCHANGE_ORDER_ID,
    }
    base["paper_lifecycle_event_id"] = stable_id("paper_lifecycle_event", base, 24)
    base["paper_lifecycle_event_sha256"] = sha256_json(base)
    return base


def _fee_model(order_notional_usdt: float, fee_bps: float) -> dict[str, Any]:
    fee_usdt = order_notional_usdt * fee_bps / 10_000.0
    return {
        "fee_model_version": "step294_review_only_fee_model_v1",
        "fee_bps": fee_bps,
        "fee_usdt": round(fee_usdt, 8),
        "fee_source": "paper_execution_config_or_default",
        "fee_model_used": True,
    }


def _slippage_model(side: str, entry_price: float, slippage_bps: float) -> dict[str, Any]:
    multiplier = 1.0 + slippage_bps / 10_000.0 if side.upper() in {"BUY", "LONG"} else 1.0 - slippage_bps / 10_000.0
    fill_price = entry_price * multiplier
    return {
        "slippage_model_version": "step294_review_only_slippage_model_v1",
        "slippage_bps": slippage_bps,
        "expected_price": round(entry_price, 8),
        "simulated_fill_price": round(fill_price, 8),
        "slippage_source": "paper_execution_config_or_default",
        "slippage_model_used": True,
    }


def _position_delta(side: str, quantity: float, fill_price: float) -> dict[str, Any]:
    signed_qty = quantity if side.upper() in {"BUY", "LONG"} else -quantity
    return {
        "position_delta_version": "step294_paper_position_delta_v1",
        "side": side.upper(),
        "quantity_delta": round(signed_qty, 12),
        "notional_delta_usdt": round(signed_qty * fill_price, 8),
        "position_opened": quantity > 0,
        "paper_only": True,
    }


def validate_paper_order_intent(order_intent: Mapping[str, Any], risk_gate_report: Mapping[str, Any] | None = None) -> tuple[bool, list[str]]:
    intent = dict(order_intent or {})
    risk_gate = dict(risk_gate_report or {})
    blockers: list[str] = []
    if intent.get("status") != "ORDER_INTENT_CREATED" or intent.get("order_intent_created") is False:
        blockers.append("ORDER_INTENT_NOT_CREATED")
    if not _text(intent.get("order_intent_id")):
        blockers.append("ORDER_INTENT_ID_MISSING")
    if not _text(intent.get("decision_id")):
        blockers.append("DECISION_ID_MISSING")
    if not _text(intent.get("risk_gate_id")):
        blockers.append("RISK_GATE_ID_MISSING")
    if not _text(intent.get("research_signal_id")):
        blockers.append("RESEARCH_SIGNAL_ID_MISSING")
    if not _text(intent.get("profile_id")):
        blockers.append("PROFILE_ID_MISSING")
    if _text(risk_gate.get("risk_gate_id")) and _text(risk_gate.get("risk_gate_id")) != _text(intent.get("risk_gate_id")):
        blockers.append("RISK_GATE_ID_MISMATCH")
    if risk_gate and risk_gate.get("approved") is not True:
        blockers.append("PRE_ORDER_RISK_GATE_NOT_APPROVED")
    if risk_gate and str(risk_gate.get("status", "")).startswith("BLOCK_"):
        blockers.append("PRE_ORDER_RISK_GATE_BLOCKED")
    if _float(intent.get("quantity"), 0.0) <= 0:
        blockers.append("QUANTITY_MISSING_OR_NON_POSITIVE")
    if _float(intent.get("entry_price") or intent.get("price") or intent.get("mark_price"), 0.0) <= 0:
        blockers.append("ENTRY_PRICE_MISSING_OR_NON_POSITIVE")
    if intent.get("external_order_submission_performed") is True or intent.get("live_order_executed") is True:
        blockers.append("LIVE_SIDE_EFFECT_FLAG_PRESENT")
    if intent.get("adapter_called") is True:
        blockers.append("ADAPTER_CALL_FLAG_PRESENT")
    return not blockers, blockers


@dataclass
class PaperExecutionRecord:
    paper_execution_id: str
    execution_id: str
    order_intent_id: str
    decision_id: str
    risk_gate_id: str
    research_signal_id: str
    profile_id: str
    status: str
    state: str
    lifecycle_states: list[str]
    lifecycle_events: list[dict[str, Any]]
    expected_order_intent: dict[str, Any]
    simulated_execution: dict[str, Any]
    simulated_fill: dict[str, Any]
    position_delta: dict[str, Any]
    fee_model: dict[str, Any]
    slippage_model: dict[str, Any]
    fill_latency_ms: float
    fill_ratio: float
    rejection_reason: str | None
    execution_blockers: list[str] = field(default_factory=list)
    order_id_chain_version: str = ORDER_ID_CHAIN_VERSION
    paper_execution_engine_version: str = PAPER_EXECUTION_ENGINE_VERSION
    pending_reconciliation: bool = True
    reconciliation_required: bool = True
    reconciliation_id: str = ""
    paper_order_submitted: bool = True
    live_order_executed: bool = False
    adapter_called: bool = False
    external_order_submission_performed: bool = False
    real_exchange_order_id: str | None = None
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)
    paper_execution_record_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("paper_execution_record_sha256"):
            payload["paper_execution_record_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "paper_execution_record_sha256"})
        return payload


def simulate_paper_execution(
    order_intent: Mapping[str, Any],
    *,
    risk_gate_report: Mapping[str, Any] | None = None,
    market_state: Mapping[str, Any] | None = None,
    execution_config: Mapping[str, Any] | None = None,
) -> PaperExecutionRecord:
    """Create a deterministic paper-only execution lifecycle.

    This function is intentionally side-effect free with respect to exchanges: no
    adapter routing, no API keys, no signed testnet execution, and no live order
    submission. It records a paper lifecycle so Step295 reconciliation can compare
    expected order intent vs simulated execution.
    """
    intent = dict(order_intent or {})
    market = dict(market_state or {})
    config = dict(execution_config or {})
    valid, blockers = validate_paper_order_intent(intent, risk_gate_report)

    order_intent_id = _text(intent.get("order_intent_id")) or order_intent_id_from_payload(intent)
    decision_id = _text(intent.get("decision_id"))
    risk_gate_id = _text(intent.get("risk_gate_id"))
    research_signal_id = _text(intent.get("research_signal_id"))
    profile_id = _text(intent.get("profile_id"))
    execution_id = execution_id_from_order_intent(order_intent_id, _text(intent.get("idempotency_key")))
    quantity = _float(intent.get("quantity"), 0.0)
    side = _text(intent.get("side") or intent.get("direction") or "BUY").upper()
    entry_price = _float(intent.get("entry_price") or intent.get("price") or intent.get("mark_price") or market.get("mark_price") or market.get("price"), 0.0)
    order_notional = _float(intent.get("order_notional_usdt") or intent.get("notional_usdt"), quantity * entry_price if quantity and entry_price else 0.0)
    fee_bps = _float(config.get("fee_bps") if "fee_bps" in config else market.get("fee_bps"), 4.0)
    slippage_bps = _float(config.get("slippage_bps") if "slippage_bps" in config else market.get("slippage_bps"), 2.0)
    fill_ratio = max(0.0, min(1.0, _float(config.get("fill_ratio"), 1.0)))
    latency_ms = max(0.0, _float(config.get("fill_latency_ms"), 0.0))

    lifecycle_events: list[dict[str, Any]] = []
    lifecycle_states = ["ORDER_INTENT_CREATED"]
    lifecycle_events.append(_event("ORDER_INTENT_CREATED", 0, "ORDER_INTENT_CREATED", "ORDER_INTENT_CREATED", {**intent, "order_intent_id": order_intent_id}))

    if not valid:
        lifecycle_states.append("PAPER_REJECTED")
        lifecycle_events.append(_event("PAPER_REJECTED", 1, "PAPER_REJECTED", STATUS_PAPER_REJECTED, {**intent, "order_intent_id": order_intent_id}))
        status = STATUS_PAPER_REJECTED
        state = "PAPER_REJECTED"
        fill_price = 0.0
        filled_qty = 0.0
        paper_submitted = False
    elif config.get("cancel_before_fill") is True:
        lifecycle_states.extend(["PAPER_SUBMITTED", "PAPER_ACCEPTED", "PAPER_CANCELLED"])
        for seq, state_name in enumerate(lifecycle_states[1:], start=1):
            lifecycle_events.append(_event(state_name, seq, state_name, state_name, {**intent, "order_intent_id": order_intent_id}))
        status = STATUS_PAPER_CANCELLED
        state = "PAPER_CANCELLED"
        fill_price = 0.0
        filled_qty = 0.0
        paper_submitted = True
    else:
        slip = _slippage_model(side, entry_price, slippage_bps)
        fill_price = float(slip["simulated_fill_price"])
        filled_qty = round(quantity * fill_ratio, 12)
        fill_state = "PAPER_FILLED" if fill_ratio >= 1.0 else "PAPER_PARTIALLY_FILLED"
        lifecycle_states.extend(["PAPER_SUBMITTED", "PAPER_ACCEPTED", fill_state, "PENDING_RECONCILIATION"])
        for seq, state_name in enumerate(lifecycle_states[1:], start=1):
            status_name = STATUS_PAPER_PENDING_RECONCILIATION if state_name == "PENDING_RECONCILIATION" else state_name
            lifecycle_events.append(_event(state_name, seq, state_name, status_name, {**intent, "order_intent_id": order_intent_id}))
        status = STATUS_PAPER_PENDING_RECONCILIATION
        state = "PENDING_RECONCILIATION"
        paper_submitted = True

    fee = _fee_model(order_notional, fee_bps)
    slip = _slippage_model(side, entry_price, slippage_bps) if valid else _slippage_model(side, entry_price or 1.0, slippage_bps)
    simulated_execution = {
        "execution_id": execution_id,
        "order_intent_id": order_intent_id,
        "execution_status": status,
        "state": state,
        "paper_submitted_at_utc": lifecycle_events[1]["event_time_utc"] if len(lifecycle_events) > 1 else None,
        "paper_accepted_at_utc": next((ev["event_time_utc"] for ev in lifecycle_events if ev["state"] == "PAPER_ACCEPTED"), None),
        "paper_filled_at_utc": next((ev["event_time_utc"] for ev in lifecycle_events if ev["state"] in {"PAPER_FILLED", "PAPER_PARTIALLY_FILLED"}), None),
        "simulated_exchange_order_id": stable_id("paper_order", {"order_intent_id": order_intent_id, "execution_id": execution_id}, 24),
        "adapter_called": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "real_exchange_order_id": REAL_EXCHANGE_ORDER_ID,
    }
    simulated_fill = {
        "execution_id": execution_id,
        "order_intent_id": order_intent_id,
        "fill_status": "NO_FILL" if not valid or status == STATUS_PAPER_CANCELLED else ("FILLED" if fill_ratio >= 1.0 else "PARTIALLY_FILLED"),
        "requested_quantity": quantity,
        "filled_quantity": filled_qty,
        "fill_ratio": fill_ratio if valid and status != STATUS_PAPER_CANCELLED else 0.0,
        "avg_fill_price": fill_price,
        "fee_usdt": fee["fee_usdt"] if valid and status != STATUS_PAPER_CANCELLED else 0.0,
        "slippage_bps": slippage_bps if valid and status != STATUS_PAPER_CANCELLED else 0.0,
        "latency_ms": latency_ms if valid and status != STATUS_PAPER_CANCELLED else 0.0,
    }
    pos_delta = _position_delta(side, filled_qty, fill_price) if filled_qty > 0 else {
        "position_delta_version": "step294_paper_position_delta_v1",
        "side": side,
        "quantity_delta": 0.0,
        "notional_delta_usdt": 0.0,
        "position_opened": False,
        "paper_only": True,
    }
    paper_execution_id = stable_id(
        "paper_exec",
        {
            "order_intent_id": order_intent_id,
            "execution_id": execution_id,
            "status": status,
            "state": state,
            "lifecycle_states": lifecycle_states,
        },
        24,
    )
    record = PaperExecutionRecord(
        paper_execution_id=paper_execution_id,
        execution_id=execution_id,
        order_intent_id=order_intent_id,
        decision_id=decision_id,
        risk_gate_id=risk_gate_id,
        research_signal_id=research_signal_id,
        profile_id=profile_id,
        status=status,
        state=state,
        lifecycle_states=lifecycle_states,
        lifecycle_events=lifecycle_events,
        expected_order_intent=dict(intent, order_intent_id=order_intent_id),
        simulated_execution=simulated_execution,
        simulated_fill=simulated_fill,
        position_delta=pos_delta,
        fee_model=fee,
        slippage_model=slip,
        fill_latency_ms=simulated_fill["latency_ms"],
        fill_ratio=simulated_fill["fill_ratio"],
        rejection_reason=";".join(blockers) if blockers else None,
        execution_blockers=blockers,
        pending_reconciliation=status == STATUS_PAPER_PENDING_RECONCILIATION,
        reconciliation_required=status == STATUS_PAPER_PENDING_RECONCILIATION,
        paper_order_submitted=paper_submitted,
    )
    record.paper_execution_record_sha256 = sha256_json({k: v for k, v in asdict(record).items() if k != "paper_execution_record_sha256"})
    return record


def build_paper_execution_registry_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    chain_payload = {
        "research_signal_id": payload.get("research_signal_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "execution_id": payload.get("execution_id"),
    }
    registry_record = {
        "paper_execution_registry_version": PAPER_EXECUTION_ENGINE_VERSION,
        "order_id_chain_version": ORDER_ID_CHAIN_VERSION,
        "paper_execution_id": payload.get("paper_execution_id"),
        "execution_id": payload.get("execution_id"),
        "order_intent_id": payload.get("order_intent_id"),
        "decision_id": payload.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id"),
        "research_signal_id": payload.get("research_signal_id"),
        "profile_id": payload.get("profile_id"),
        "status": payload.get("status"),
        "state": payload.get("state"),
        "lifecycle_states": payload.get("lifecycle_states", []),
        "lifecycle_event_count": len(payload.get("lifecycle_events", []) or []),
        "fill_status": (payload.get("simulated_fill") or {}).get("fill_status"),
        "filled_quantity": (payload.get("simulated_fill") or {}).get("filled_quantity"),
        "avg_fill_price": (payload.get("simulated_fill") or {}).get("avg_fill_price"),
        "fee_usdt": (payload.get("simulated_fill") or {}).get("fee_usdt"),
        "slippage_bps": (payload.get("simulated_fill") or {}).get("slippage_bps"),
        "latency_ms": (payload.get("simulated_fill") or {}).get("latency_ms"),
        "pending_reconciliation": payload.get("pending_reconciliation"),
        "reconciliation_required": payload.get("reconciliation_required"),
        "execution_chain_complete": chain_complete(chain_payload, through="execution"),
        "missing_execution_chain_fields": missing_chain_fields(chain_payload, through="execution"),
        "paper_order_submitted": payload.get("paper_order_submitted"),
        "adapter_called": payload.get("adapter_called"),
        "live_order_executed": payload.get("live_order_executed"),
        "external_order_submission_performed": payload.get("external_order_submission_performed"),
        "runtime_settings_mutated": payload.get("runtime_settings_mutated"),
        "score_weights_mutated": payload.get("score_weights_mutated"),
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    registry_record["paper_execution_registry_record_id"] = stable_id("paper_execution_registry", registry_record, 24)
    registry_record["paper_execution_registry_record_sha256"] = sha256_json(registry_record)
    return registry_record


def persist_paper_execution_record(cfg: AppConfig, record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    latest_record_path = _latest_path(cfg, "paper_execution_record.json")
    latest_events_path = _latest_path(cfg, "paper_execution_lifecycle_events.json")
    latest_registry_path = _latest_path(cfg, "paper_execution_registry_record.json")
    atomic_write_json(latest_record_path, payload)
    atomic_write_json(latest_events_path, payload.get("lifecycle_events", []))
    registry_record = build_paper_execution_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, PAPER_EXECUTION_REGISTRY_NAME),
        registry_record,
        registry_name=PAPER_EXECUTION_REGISTRY_NAME,
        id_field="paper_execution_registry_record_id",
        hash_field="paper_execution_registry_record_sha256",
        id_prefix="paper_execution_registry",
    )
    atomic_write_json(latest_registry_path, persisted)
    return persisted


def execute_and_persist_paper_order(
    order_intent: Mapping[str, Any],
    *,
    risk_gate_report: Mapping[str, Any] | None = None,
    market_state: Mapping[str, Any] | None = None,
    execution_config: Mapping[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    record = simulate_paper_execution(
        order_intent,
        risk_gate_report=risk_gate_report,
        market_state=market_state,
        execution_config=execution_config,
    ).to_dict()
    registry_record = persist_paper_execution_record(cfg, record)
    record["paper_execution_registry_record_id"] = registry_record.get("paper_execution_registry_record_id")
    record["paper_execution_registry_record_sha256"] = registry_record.get("paper_execution_registry_record_sha256")
    atomic_write_json(_latest_path(cfg, "paper_execution_record.json"), record)
    return record
