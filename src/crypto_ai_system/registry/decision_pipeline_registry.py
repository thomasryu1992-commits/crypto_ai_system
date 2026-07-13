from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.trading.order_id_chain import ORDER_ID_CHAIN_VERSION
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

DECISION_PIPELINE_REGISTRY_VERSION = "step291_decision_pipeline_registry_v1"

FULL_CANONICAL_ID_CHAIN = (
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
    "outcome_id",
    "feedback_cycle_id",
)

DECISION_STAGE_REQUIRED_ID_CHAIN = (
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "decision_id",
)

STAGE_REQUIRED_ID_CHAIN = {
    "review_only": DECISION_STAGE_REQUIRED_ID_CHAIN,
    "shadow": DECISION_STAGE_REQUIRED_ID_CHAIN,
    "paper": DECISION_STAGE_REQUIRED_ID_CHAIN + ("risk_gate_id", "order_intent_id"),
    "signed_testnet": DECISION_STAGE_REQUIRED_ID_CHAIN + ("approval_packet_id", "approval_intake_id", "risk_gate_id", "order_intent_id"),
    "live_canary": DECISION_STAGE_REQUIRED_ID_CHAIN + ("approval_packet_id", "approval_intake_id", "risk_gate_id", "order_intent_id", "execution_id", "reconciliation_id"),
    "live_scaled": FULL_CANONICAL_ID_CHAIN,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "allowed"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _stage(decision: Mapping[str, Any], trade_decision: Mapping[str, Any], risk_gate: Mapping[str, Any], order_intent: Mapping[str, Any], execution: Mapping[str, Any], reconciliation: Mapping[str, Any]) -> str:
    explicit = _first(
        decision.get("decision_stage"),
        trade_decision.get("decision_stage"),
        order_intent.get("decision_stage"),
        execution.get("decision_stage"),
        reconciliation.get("decision_stage"),
    ).lower()
    if explicit:
        return explicit
    if _text(execution.get("execution_id")) or _text(reconciliation.get("reconciliation_id")):
        return "paper"
    if _text(order_intent.get("order_intent_id")) or order_intent.get("status") == "ORDER_INTENT_CREATED":
        return "paper"
    if _text(risk_gate.get("risk_gate_id")):
        return "shadow"
    return "review_only"


def _permission_result(decision: Mapping[str, Any], research_signal: Mapping[str, Any], signal_qa_report: Mapping[str, Any], legacy_blocker: Mapping[str, Any], trade_decision: Mapping[str, Any]) -> str:
    if _text(trade_decision.get("final_decision")):
        return _text(trade_decision.get("final_decision"))
    if _text(decision.get("permission_result")):
        return _text(decision.get("permission_result"))
    if _text(research_signal.get("permission_result")):
        return _text(research_signal.get("permission_result"))
    if _text(signal_qa_report.get("signal_qa_result")):
        return _text(signal_qa_report.get("signal_qa_result"))
    if _text(legacy_blocker.get("legacy_signal_fallback_blocker_result")):
        return _text(legacy_blocker.get("legacy_signal_fallback_blocker_result"))
    if _bool(decision.get("allow_new_position")):
        return "allow_new_position"
    return "review_only"


def _direction(decision: Mapping[str, Any], research_signal: Mapping[str, Any], trade_decision: Mapping[str, Any], order_intent: Mapping[str, Any]) -> str:
    return _first(
        order_intent.get("direction"),
        trade_decision.get("direction"),
        decision.get("direction"),
        decision.get("side"),
        research_signal.get("entry_side"),
        "NONE",
    ).upper()


def _id_chain(ids: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(ids.get(field)) for field in FULL_CANONICAL_ID_CHAIN}


def _missing(fields: tuple[str, ...], payload: Mapping[str, Any]) -> list[str]:
    return [field for field in fields if not _text(payload.get(field))]


def build_decision_pipeline_registry_record(
    *,
    decision: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
    signal_qa_report: Mapping[str, Any] | None = None,
    legacy_blocker: Mapping[str, Any] | None = None,
    trade_decision: Mapping[str, Any] | None = None,
    risk_gate: Mapping[str, Any] | None = None,
    order_intent: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
    reconciliation: Mapping[str, Any] | None = None,
    outcome: Mapping[str, Any] | None = None,
    feedback: Mapping[str, Any] | None = None,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical Step291 decision pipeline registry row.

    The row is audit evidence only. It never creates order intent, never routes
    orders, never mutates settings, and never promotes a profile. Missing future
    IDs are preserved as explicit missing-chain fields rather than being guessed.
    """
    decision = dict(decision or {})
    research_signal = dict(research_signal or {})
    signal_qa_report = dict(signal_qa_report or {})
    legacy_blocker = dict(legacy_blocker or {})
    trade_decision = dict(trade_decision or {})
    risk_gate = dict(risk_gate or {})
    order_intent = dict(order_intent or {})
    execution = dict(execution or {})
    reconciliation = dict(reconciliation or {})
    outcome = dict(outcome or {})
    feedback = dict(feedback or {})
    approval = dict(approval or {})

    decision_stage = _stage(decision, trade_decision, risk_gate, order_intent, execution, reconciliation)
    ids = {
        "data_snapshot_id": _first(decision.get("data_snapshot_id"), research_signal.get("data_snapshot_id"), trade_decision.get("data_snapshot_id")),
        "feature_snapshot_id": _first(decision.get("feature_snapshot_id"), research_signal.get("feature_snapshot_id"), trade_decision.get("feature_snapshot_id")),
        "research_signal_id": _first(decision.get("research_signal_id"), research_signal.get("research_signal_id"), research_signal.get("signal_id"), signal_qa_report.get("research_signal_id")),
        "profile_id": _first(decision.get("profile_id"), research_signal.get("profile_id"), approval.get("profile_id")),
        "approval_packet_id": _first(decision.get("approval_packet_id"), approval.get("approval_packet_id"), trade_decision.get("approval_packet_id")),
        "approval_intake_id": _first(decision.get("approval_intake_id"), approval.get("approval_intake_id"), trade_decision.get("approval_intake_id")),
        "decision_id": _first(decision.get("decision_id"), trade_decision.get("decision_id"), order_intent.get("decision_id")),
        "risk_gate_id": _first(decision.get("risk_gate_id"), risk_gate.get("risk_gate_id"), trade_decision.get("risk_gate_id"), order_intent.get("risk_gate_id")),
        "order_intent_id": _first(order_intent.get("order_intent_id"), order_intent.get("intent_id"), trade_decision.get("order_intent_id")),
        "execution_id": _first(execution.get("execution_id"), execution.get("exchange_order_id"), execution.get("simulated_execution_id")),
        "reconciliation_id": _first(reconciliation.get("reconciliation_id")),
        "outcome_id": _first(outcome.get("outcome_id")),
        "feedback_cycle_id": _first(feedback.get("feedback_cycle_id"), outcome.get("feedback_cycle_id")),
    }
    id_chain = _id_chain(ids)
    full_missing = _missing(FULL_CANONICAL_ID_CHAIN, id_chain)
    current_required = STAGE_REQUIRED_ID_CHAIN.get(decision_stage, DECISION_STAGE_REQUIRED_ID_CHAIN)
    current_missing = _missing(current_required, id_chain)
    block_reasons = []
    for source in (decision, trade_decision, signal_qa_report, legacy_blocker, risk_gate, reconciliation):
        raw = source.get("block_reasons") or source.get("reasons") or source.get("problems") or []
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, (list, tuple, set)):
            block_reasons.extend([str(item) for item in raw if item])

    record = {
        "decision_pipeline_registry_version": DECISION_PIPELINE_REGISTRY_VERSION,
        "chain_version": ORDER_ID_CHAIN_VERSION,
        **id_chain,
        "decision_stage": decision_stage,
        "decision_status": _first(trade_decision.get("final_decision"), decision.get("risk_level"), decision.get("research_bias"), "review_only"),
        "direction": _direction(decision, research_signal, trade_decision, order_intent),
        "entry": decision.get("entry") or decision.get("entry_price") or research_signal.get("entry") or research_signal.get("entry_price"),
        "stop_loss": decision.get("stop_loss") or research_signal.get("stop_loss"),
        "take_profit": decision.get("take_profit") or research_signal.get("take_profit"),
        "risk_reward": decision.get("risk_reward") or research_signal.get("risk_reward"),
        "permission_result": _permission_result(decision, research_signal, signal_qa_report, legacy_blocker, trade_decision),
        "signal_qa_result": signal_qa_report.get("signal_qa_result"),
        "legacy_signal_fallback_blocker_result": legacy_blocker.get("legacy_signal_fallback_blocker_result"),
        "signal_permission_authoritative": bool(decision.get("signal_permission_authoritative", False)),
        "allow_long": bool(decision.get("allow_long", False)),
        "allow_short": bool(decision.get("allow_short", False)),
        "allow_new_position": bool(decision.get("allow_new_position", False)),
        "allow_order_intent": bool(trade_decision.get("allow_order_intent", False)),
        "risk_gate_status": _first(risk_gate.get("status"), risk_gate.get("risk_level")),
        "order_intent_status": _first(order_intent.get("status")),
        "execution_status": _first(execution.get("status")),
        "reconciliation_status": _first(reconciliation.get("status")),
        "block_reasons": sorted(set(block_reasons)),
        "canonical_id_chain": id_chain,
        "canonical_id_chain_required_fields": list(FULL_CANONICAL_ID_CHAIN),
        "missing_canonical_id_fields": full_missing,
        "current_stage_required_id_fields": list(current_required),
        "missing_current_stage_id_fields": current_missing,
        "current_stage_id_chain_complete": len(current_missing) == 0,
        "full_canonical_id_chain_complete": len(full_missing) == 0,
        "approval_chain_complete": bool(id_chain["approval_packet_id"] and id_chain["approval_intake_id"]),
        "order_lifecycle_chain_complete": bool(id_chain["decision_id"] and id_chain["risk_gate_id"] and id_chain["order_intent_id"]),
        "execution_chain_complete": bool(id_chain["order_intent_id"] and id_chain["execution_id"] and id_chain["reconciliation_id"]),
        "live_candidate_eligible": bool(research_signal.get("live_candidate_eligible", False)),
        "order_intent_created": bool(order_intent.get("status") == "ORDER_INTENT_CREATED" or order_intent.get("state") == "CREATED"),
        "trade_approved": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "external_order_submission_performed": False,
        "created_at_utc": _first(decision.get("created_at_utc"), research_signal.get("created_at_utc"), utc_now_canonical()),
    }
    record["decision_pipeline_record_id"] = stable_id("decision_pipeline", record, 24)
    record["decision_pipeline_registry_record_sha256"] = sha256_json(record)
    return record


def persist_decision_pipeline_registry_record(
    cfg: AppConfig,
    *,
    decision: Mapping[str, Any] | None = None,
    research_signal: Mapping[str, Any] | None = None,
    signal_qa_report: Mapping[str, Any] | None = None,
    legacy_blocker: Mapping[str, Any] | None = None,
    trade_decision: Mapping[str, Any] | None = None,
    risk_gate: Mapping[str, Any] | None = None,
    order_intent: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
    reconciliation: Mapping[str, Any] | None = None,
    outcome: Mapping[str, Any] | None = None,
    feedback: Mapping[str, Any] | None = None,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_decision_pipeline_registry_record(
        decision=decision,
        research_signal=research_signal,
        signal_qa_report=signal_qa_report,
        legacy_blocker=legacy_blocker,
        trade_decision=trade_decision,
        risk_gate=risk_gate,
        order_intent=order_intent,
        execution=execution,
        reconciliation=reconciliation,
        outcome=outcome,
        feedback=feedback,
        approval=approval,
    )
    return append_registry_record(
        registry_path(cfg, "decision_pipeline_registry"),
        record,
        registry_name="decision_pipeline_registry",
        id_field="decision_pipeline_record_id",
        hash_field="decision_pipeline_registry_record_sha256",
        id_prefix="decision_pipeline",
    )
