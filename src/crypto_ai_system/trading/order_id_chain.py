from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from crypto_ai_system.utils.audit import stable_id

ORDER_ID_CHAIN_VERSION = "step271_canonical_decision_risk_order_chain_v1"
CANONICAL_ORDER_ID_FIELDS = (
    "research_signal_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
    "outcome_id",
    "feedback_cycle_id",
)


@dataclass(frozen=True)
class CanonicalOrderIdChain:
    research_signal_id: str
    decision_id: str
    risk_gate_id: str
    order_intent_id: str
    execution_id: str = ""
    reconciliation_id: str = ""
    outcome_id: str = ""
    feedback_cycle_id: str = ""
    profile_id: str = ""
    chain_version: str = ORDER_ID_CHAIN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def decision_id_from_signal(research_signal: Mapping[str, Any] | None, decision_payload: Mapping[str, Any] | None = None) -> str:
    signal = dict(research_signal or {})
    payload = dict(decision_payload or {})
    existing = _text(payload.get("decision_id")) or _text(signal.get("decision_id"))
    if existing:
        return existing
    return stable_id(
        "decision",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "research_signal_id": signal.get("research_signal_id") or signal.get("signal_id"),
            "profile_id": signal.get("profile_id"),
            "entry_side": signal.get("entry_side") or payload.get("side"),
            "trade_permission": signal.get("trade_permission"),
            "feature_snapshot_id": signal.get("feature_snapshot_id"),
            "created_from": payload.get("created_from", "step271_decision"),
        },
        24,
    )


def risk_gate_id_from_payload(decision: Mapping[str, Any], research_signal: Mapping[str, Any], profile: Mapping[str, Any], gate_payload: Mapping[str, Any]) -> str:
    existing = _text(gate_payload.get("risk_gate_id"))
    if existing:
        return existing
    return stable_id(
        "risk_gate",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "decision_id": decision.get("decision_id"),
            "research_signal_id": research_signal.get("research_signal_id") or research_signal.get("signal_id"),
            "profile_id": profile.get("profile_id") or research_signal.get("profile_id"),
            "block_reasons": gate_payload.get("block_reasons", []),
            "reduce_reasons": gate_payload.get("reduce_reasons", []),
            "risk_level": gate_payload.get("risk_level"),
        },
        24,
    )


def order_intent_id_from_payload(payload: Mapping[str, Any]) -> str:
    existing = _text(payload.get("order_intent_id")) or _text(payload.get("dry_run_order_intent_id"))
    if existing and not existing.startswith("pdoi_"):
        return existing
    return stable_id(
        "order_intent",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "decision_id": payload.get("decision_id"),
            "risk_gate_id": payload.get("risk_gate_id"),
            "research_signal_id": payload.get("research_signal_id"),
            "source_event_id": payload.get("source_event_id"),
            "observation_id": payload.get("observation_id"),
            "idempotency_key": payload.get("idempotency_key"),
            "side": payload.get("side"),
            "entry_price": payload.get("entry_price"),
            "quantity": payload.get("quantity"),
        },
        24,
    )


def execution_id_from_order_intent(order_intent_id: str, idempotency_key: str = "", simulated_order_id: str = "") -> str:
    existing = _text(simulated_order_id)
    if existing and not existing.startswith("spo_"):
        return existing
    return stable_id(
        "execution",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "order_intent_id": order_intent_id,
            "idempotency_key": idempotency_key,
            "simulated_order_id": simulated_order_id,
        },
        24,
    )


def reconciliation_id_from_execution(order_intent_id: str, execution_id: str) -> str:
    return stable_id(
        "rec",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "order_intent_id": order_intent_id,
            "execution_id": execution_id,
        },
        24,
    )


def outcome_id_from_reconciliation(reconciliation_id: str, close_r: Any = "", close_reason: Any = "") -> str:
    return stable_id(
        "out",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "reconciliation_id": reconciliation_id,
            "simulated_close_r": close_r,
            "simulated_close_reason": close_reason,
        },
        24,
    )


def feedback_cycle_id_from_outcome(outcome_id: str, profile_id: str = "", research_signal_id: str = "") -> str:
    return stable_id(
        "fbc",
        {
            "chain_version": ORDER_ID_CHAIN_VERSION,
            "outcome_id": outcome_id,
            "profile_id": profile_id,
            "research_signal_id": research_signal_id,
        },
        24,
    )


def chain_complete(payload: Mapping[str, Any], *, through: str = "outcome") -> bool:
    required_by_stage = {
        "decision": ("research_signal_id", "decision_id"),
        "risk_gate": ("research_signal_id", "decision_id", "risk_gate_id"),
        "order_intent": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id"),
        "execution": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id"),
        "reconciliation": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id", "reconciliation_id"),
        "outcome": CANONICAL_ORDER_ID_FIELDS,
    }
    fields = required_by_stage.get(through, CANONICAL_ORDER_ID_FIELDS)
    return all(_text(payload.get(field)) for field in fields)


def missing_chain_fields(payload: Mapping[str, Any], *, through: str = "outcome") -> list[str]:
    required_by_stage = {
        "decision": ("research_signal_id", "decision_id"),
        "risk_gate": ("research_signal_id", "decision_id", "risk_gate_id"),
        "order_intent": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id"),
        "execution": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id"),
        "reconciliation": ("research_signal_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id", "reconciliation_id"),
        "outcome": CANONICAL_ORDER_ID_FIELDS,
    }
    fields = required_by_stage.get(through, CANONICAL_ORDER_ID_FIELDS)
    return [field for field in fields if not _text(payload.get(field))]
