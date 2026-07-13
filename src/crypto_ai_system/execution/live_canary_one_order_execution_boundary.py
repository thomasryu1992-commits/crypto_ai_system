from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.live_read_only_canary_preparation import (
    STATUS_READY_REVIEW_ONLY as P9_READY,
    build_valid_p9_fixture_sources,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_VERSION = "p10_live_canary_one_order_execution_boundary_v1"
P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_REGISTRY_NAME = "p10_live_canary_one_order_execution_boundary_registry"

STATUS_WAITING_REVIEW_ONLY = "P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_WAITING_REVIEW_ONLY"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_BLOCKED_FAIL_CLOSED"

EXACT_APPROVAL_PHRASE = "I APPROVE REVIEWING EXACTLY ONE BTCUSDT LIVE CANARY ORDER BOUNDARY WITHOUT SUBMIT"

_ALLOWED_SIDES = {"BUY", "SELL"}
_ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT"}

_ALWAYS_DISABLED = {
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
    "external_order_submission_performed": False,
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "signed_order_executor_enabled": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "candidate_profile_applied": False,
    "auto_promotion_allowed": False,
    "secret_value_accessed": False,
    "secret_value_logged": False,
    "api_key_value_logged": False,
    "api_secret_value_logged": False,
    "private_key_logged": False,
    "passphrase_logged": False,
    "secret_file_accessed": False,
    "secret_file_created": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
    "live_execution_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_submission_allowed": False,
    "live_order_endpoint_called": False,
    "live_order_status_endpoint_called": False,
    "live_cancel_endpoint_called": False,
    "order_endpoint_called": False,
    "order_status_endpoint_called": False,
    "cancel_endpoint_called": False,
    "http_request_sent": False,
    "signature_created": False,
    "signed_request_created": False,
    "actual_live_order_submitted": False,
    "actual_order_submission_performed": False,
    "live_canary_order_submitted": False,
    "mainnet_key_scope_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
}

_SECRET_FIELDS = (
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "private_key_logged",
    "passphrase_logged",
    "secret_file_accessed",
    "secret_file_created",
    "secret_value_read",
    "secret_bytes_read",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
)

_ENDPOINT_FIELDS = (
    "live_order_endpoint_called",
    "live_order_status_endpoint_called",
    "live_cancel_endpoint_called",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_live_order_submitted",
    "actual_order_submission_performed",
    "external_order_submission_performed",
    "live_canary_order_submitted",
)

_UNSAFE_FLAG_FIELDS = (
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "external_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "withdrawal_enabled",
    "transfer_enabled",
    "admin_enabled",
    "leverage_mutation_enabled",
    "margin_mode_mutation_enabled",
)

_REQUIRED_CHAIN_FIELDS = (
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED)
    payload.update(
        {
            "p10_live_canary_one_order_execution_boundary_ready": False,
            "live_canary_approval_packet_valid_review_only": False,
            "live_canary_one_order_boundary_valid": False,
            "live_canary_runtime_submit_action_created": False,
            "post_submit_relock_required": True,
            "post_submit_relock_confirmed": False,
        }
    )
    return payload


def _artifact_hash(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    for key in keys:
        if data.get(key):
            return str(data[key])
    if not data:
        return None
    return sha256_json(data)


def _summary(payload: Mapping[str, Any], *, name: str, hash_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status"),
        "sha256": _artifact_hash(data, *hash_keys),
        "block_reasons": list(data.get("block_reasons") or data.get("blocked_reasons") or []),
    }


@dataclass(frozen=True)
class LiveCanaryBoundaryApprovalRequest:
    requested_stage: str = "live_canary_one_order_execution_boundary"
    operator_id: str = "operator_thomas_review_only"
    ticket_or_signature: str = field(default_factory=lambda: f"LIVE-CANARY-BOUNDARY-{stable_id('p10_ticket', {'stage': 'p10'}, 8)}")
    exact_approval_phrase: str = EXACT_APPROVAL_PHRASE
    acknowledged_no_live_submit_in_this_package: bool = True
    acknowledged_separate_runtime_action_required_for_submit: bool = True
    acknowledged_live_scaled_remains_disabled: bool = True
    request_live_order_submission_enabled: bool = False
    request_place_order_enabled: bool = False
    request_cancel_order_enabled: bool = False
    kill_switch_rechecked: bool = True
    manual_kill_switch_active: bool = False
    hard_cap_rechecked: bool = True
    monitoring_alerting_ready: bool = True
    rollback_runbook_ready: bool = True
    max_live_canary_order_count: int = 1
    max_live_canary_notional_usdt: float = 5.0
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCanaryOneOrderIntent:
    environment: str = "live_canary"
    venue: str = "binance_futures_live"
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: float = 0.001
    reference_price: float = 50000.0
    notional_usdt: float = 5.0
    max_notional_usdt: float = 5.0
    max_order_count: int = 1
    orders_already_submitted: int = 0
    idempotency_key: str = field(default_factory=lambda: stable_id("p10_live_canary_idempotency", {"symbol": "BTCUSDT"}, 24))
    idempotency_key_seen_before: bool = False
    duplicate_submit_lock_engaged: bool = True
    post_submit_relock_planned: bool = True
    fresh_data_snapshot: bool = True
    data_snapshot_stale: bool = False
    source_qa_passed: bool = True
    research_signal_v2_created: bool = True
    signal_qa_passed: bool = True
    trading_decision_created: bool = True
    hot_path_preorder_risk_gate_passed: bool = True
    hot_path_preorder_risk_gate_fresh: bool = True
    risk_gate_stage: str = "live_canary"
    price_source_hard_required_present: bool = True
    fallback_or_synthetic_or_sample_data_used: bool = False
    data_snapshot_id: str = "data_snapshot_live_canary_fixture"
    feature_snapshot_id: str = "feature_snapshot_live_canary_fixture"
    research_signal_id: str = "research_signal_live_canary_fixture"
    profile_id: str = "profile_live_canary_fixture"
    approval_packet_id: str = "approval_packet_live_canary_fixture"
    approval_intake_id: str = "approval_intake_live_canary_fixture"
    decision_id: str = "decision_live_canary_fixture"
    risk_gate_id: str = "risk_gate_live_canary_fixture"
    order_intent_id: str = "order_intent_live_canary_fixture"
    live_order_endpoint_called: bool = False
    live_order_status_endpoint_called: bool = False
    live_cancel_endpoint_called: bool = False
    http_request_sent: bool = False
    signature_created: bool = False
    signed_request_created: bool = False
    actual_live_order_submitted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_p10_live_canary_one_order_execution_boundary(
    *,
    p9_report: Mapping[str, Any] | None = None,
    approval_request: Mapping[str, Any] | None = None,
    order_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    p9 = dict(p9_report or {})
    request = dict(approval_request or {})
    intent = dict(order_intent or {})
    blockers: list[str] = []
    warnings: list[str] = []

    if p9.get("status") != P9_READY or p9.get("live_canary_preparation_ready_for_manual_approval_packet") is not True:
        blockers.append("P10_BLOCK_P9_LIVE_CANARY_PREPARATION_NOT_READY")
    if p9.get("live_canary_execution_enabled") is not False or p9.get("live_scaled_execution_enabled") is not False:
        blockers.append("P10_BLOCK_P9_UNSAFE_LIVE_FLAGS")
    if _bool(p9.get("secret_value_accessed")) or _bool(p9.get("secret_value_logged")):
        blockers.append("P10_BLOCK_P9_SECRET_LEAK")
    if _bool(p9.get("actual_live_order_submitted")) or _bool(p9.get("live_order_endpoint_called")):
        blockers.append("P10_BLOCK_P9_ALREADY_PERFORMED_LIVE_SUBMIT_OR_ENDPOINT_CALL")

    if not request:
        blockers.append("P10_BLOCK_OPERATOR_BOUNDARY_APPROVAL_REQUEST_MISSING")
    else:
        if request.get("requested_stage") != "live_canary_one_order_execution_boundary":
            blockers.append("P10_BLOCK_OPERATOR_REQUEST_STAGE_INVALID")
        if not _nonempty(request.get("operator_id")):
            blockers.append("P10_BLOCK_OPERATOR_ID_MISSING")
        if not _nonempty(request.get("ticket_or_signature")):
            blockers.append("P10_BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING")
        if request.get("exact_approval_phrase") != EXACT_APPROVAL_PHRASE:
            blockers.append("P10_BLOCK_EXACT_APPROVAL_PHRASE_MISSING_OR_INVALID")
        if request.get("acknowledged_no_live_submit_in_this_package") is not True:
            blockers.append("P10_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_NO_LIVE_SUBMIT")
        if request.get("acknowledged_separate_runtime_action_required_for_submit") is not True:
            blockers.append("P10_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_SEPARATE_RUNTIME_ACTION")
        if request.get("acknowledged_live_scaled_remains_disabled") is not True:
            blockers.append("P10_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_LIVE_SCALED_DISABLED")
        if _bool(request.get("request_live_order_submission_enabled")) or _bool(request.get("request_place_order_enabled")) or _bool(request.get("request_cancel_order_enabled")):
            blockers.append("P10_BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_ENABLEMENT")
        if request.get("kill_switch_rechecked") is not True:
            blockers.append("P10_BLOCK_KILL_SWITCH_NOT_RECHECKED")
        if _bool(request.get("manual_kill_switch_active")):
            blockers.append("P10_BLOCK_MANUAL_KILL_SWITCH_ACTIVE")
        if request.get("hard_cap_rechecked") is not True:
            blockers.append("P10_BLOCK_HARD_CAP_NOT_RECHECKED")
        if request.get("monitoring_alerting_ready") is not True:
            blockers.append("P10_BLOCK_MONITORING_ALERTING_NOT_READY")
        if request.get("rollback_runbook_ready") is not True:
            blockers.append("P10_BLOCK_ROLLBACK_RUNBOOK_NOT_READY")
        if int(request.get("max_live_canary_order_count") or 0) != 1:
            blockers.append("P10_BLOCK_MAX_LIVE_CANARY_ORDER_COUNT_NOT_ONE")
        req_cap = _as_float(request.get("max_live_canary_notional_usdt"))
        if req_cap is None or req_cap <= 0 or req_cap > 5:
            blockers.append("P10_BLOCK_MAX_LIVE_CANARY_NOTIONAL_INVALID")

    if not intent:
        blockers.append("P10_BLOCK_LIVE_CANARY_ONE_ORDER_INTENT_MISSING")
    else:
        if intent.get("environment") != "live_canary":
            blockers.append("P10_BLOCK_ORDER_INTENT_ENVIRONMENT_NOT_LIVE_CANARY")
        if intent.get("venue") != "binance_futures_live":
            blockers.append("P10_BLOCK_ORDER_INTENT_VENUE_INVALID")
        if intent.get("symbol") != "BTCUSDT":
            blockers.append("P10_BLOCK_ORDER_INTENT_SYMBOL_NOT_BTCUSDT")
        if str(intent.get("side") or "").upper() not in _ALLOWED_SIDES:
            blockers.append("P10_BLOCK_ORDER_INTENT_SIDE_INVALID")
        if str(intent.get("order_type") or "").upper() not in _ALLOWED_ORDER_TYPES:
            blockers.append("P10_BLOCK_ORDER_INTENT_TYPE_INVALID")
        qty = _as_float(intent.get("quantity"))
        ref_price = _as_float(intent.get("reference_price"))
        notional = _as_float(intent.get("notional_usdt"))
        cap = _as_float(intent.get("max_notional_usdt"))
        if qty is None or qty <= 0:
            blockers.append("P10_BLOCK_ORDER_INTENT_QUANTITY_INVALID")
        if ref_price is None or ref_price <= 0:
            blockers.append("P10_BLOCK_ORDER_INTENT_REFERENCE_PRICE_INVALID")
        if notional is None or notional <= 0:
            blockers.append("P10_BLOCK_ORDER_INTENT_NOTIONAL_INVALID")
        if cap is None or cap <= 0 or cap > 5:
            blockers.append("P10_BLOCK_ORDER_INTENT_CAP_INVALID")
        if notional is not None and cap is not None and notional > cap:
            blockers.append("P10_BLOCK_ORDER_INTENT_NOTIONAL_EXCEEDS_CAP")
        if int(intent.get("max_order_count") or 0) != 1:
            blockers.append("P10_BLOCK_ORDER_INTENT_MAX_ORDER_COUNT_NOT_ONE")
        if int(intent.get("orders_already_submitted") or 0) != 0:
            blockers.append("P10_BLOCK_ORDER_ALREADY_SUBMITTED")
        if not _nonempty(intent.get("idempotency_key")):
            blockers.append("P10_BLOCK_IDEMPOTENCY_KEY_MISSING")
        if _bool(intent.get("idempotency_key_seen_before")):
            blockers.append("P10_BLOCK_DUPLICATE_IDEMPOTENCY_KEY")
        if intent.get("duplicate_submit_lock_engaged") is not True:
            blockers.append("P10_BLOCK_DUPLICATE_SUBMIT_LOCK_NOT_ENGAGED")
        if intent.get("post_submit_relock_planned") is not True:
            blockers.append("P10_BLOCK_POST_SUBMIT_RELOCK_NOT_PLANNED")
        if intent.get("fresh_data_snapshot") is not True or _bool(intent.get("data_snapshot_stale")):
            blockers.append("P10_BLOCK_FRESH_DATA_SNAPSHOT_NOT_VALID")
        if intent.get("source_qa_passed") is not True or intent.get("price_source_hard_required_present") is not True:
            blockers.append("P10_BLOCK_SOURCE_QA_OR_PRICE_HARD_REQUIRED_NOT_VALID")
        if _bool(intent.get("fallback_or_synthetic_or_sample_data_used")):
            blockers.append("P10_BLOCK_FALLBACK_SYNTHETIC_SAMPLE_DATA_USED")
        if intent.get("research_signal_v2_created") is not True or intent.get("signal_qa_passed") is not True:
            blockers.append("P10_BLOCK_RESEARCH_SIGNAL_OR_SIGNAL_QA_NOT_VALID")
        if intent.get("trading_decision_created") is not True:
            blockers.append("P10_BLOCK_TRADING_DECISION_MISSING")
        if intent.get("hot_path_preorder_risk_gate_passed") is not True or intent.get("hot_path_preorder_risk_gate_fresh") is not True:
            blockers.append("P10_BLOCK_HOT_PATH_PREORDER_RISK_GATE_NOT_FRESH_PASS")
        if intent.get("risk_gate_stage") != "live_canary":
            blockers.append("P10_BLOCK_RISK_GATE_STAGE_NOT_LIVE_CANARY")
        missing_chain = [field for field in _REQUIRED_CHAIN_FIELDS if not _nonempty(intent.get(field))]
        if missing_chain:
            blockers.append("P10_BLOCK_CANONICAL_ID_CHAIN_INCOMPLETE")
        for field in _ENDPOINT_FIELDS:
            if _bool(intent.get(field)):
                blockers.append(f"P10_BLOCK_{field.upper()}_NOT_FALSE")

    for source_name, source in (("p9", p9), ("approval_request", request), ("order_intent", intent)):
        for field in _SECRET_FIELDS:
            if _bool(source.get(field)):
                blockers.append(f"P10_BLOCK_{source_name.upper()}_{field.upper()}_SECRET_ACCESS")
        for field in _UNSAFE_FLAG_FIELDS:
            if _bool(source.get(field)):
                blockers.append(f"P10_BLOCK_{source_name.upper()}_{field.upper()}_UNSAFE_FLAG")

    valid = not blockers
    if valid:
        warnings.append("P10_REVIEW_ONLY_BOUNDARY_VALID_BUT_NO_LIVE_SUBMIT_PERFORMED")

    return {
        "artifact_type": "p10_live_canary_one_order_execution_boundary_validation",
        "valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "warnings": sorted(dict.fromkeys(warnings)),
        "p9_live_canary_preparation_ready": p9.get("status") == P9_READY and p9.get("live_canary_preparation_ready_for_manual_approval_packet") is True,
        "approval_request_valid": bool(request) and request.get("exact_approval_phrase") == EXACT_APPROVAL_PHRASE,
        "one_order_intent_valid": bool(intent) and not any(reason.startswith("P10_BLOCK_ORDER_INTENT") for reason in blockers),
        "hot_path_preorder_risk_gate_valid": intent.get("hot_path_preorder_risk_gate_passed") is True and intent.get("hot_path_preorder_risk_gate_fresh") is True,
        "idempotency_and_duplicate_lock_valid": bool(intent.get("idempotency_key")) and intent.get("duplicate_submit_lock_engaged") is True and intent.get("idempotency_key_seen_before") is False,
        "post_submit_relock_planned": intent.get("post_submit_relock_planned") is True,
        **_disabled_payload(),
    }


def build_p10_live_canary_one_order_execution_boundary_report(
    *,
    cfg: AppConfig | None = None,
    p9_report: Mapping[str, Any] | None = None,
    approval_request: Mapping[str, Any] | None = None,
    order_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p9 = dict(p9_report or _read_latest_json(cfg, "p9_live_read_only_canary_preparation_report.json"))
    request = dict(approval_request or {})
    intent = dict(order_intent or {})
    validation = validate_p10_live_canary_one_order_execution_boundary(p9_report=p9, approval_request=request, order_intent=intent)

    p9_waiting = p9.get("status") != P9_READY
    if validation["valid"]:
        status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT
        blocked = False
        fail_closed = False
    elif p9_waiting:
        status = STATUS_WAITING_REVIEW_ONLY
        blocked = True
        fail_closed = True
    else:
        status = STATUS_BLOCKED_FAIL_CLOSED
        blocked = True
        fail_closed = True

    report = {
        "artifact_type": "p10_live_canary_one_order_execution_boundary",
        "p10_live_canary_one_order_execution_boundary_version": P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": fail_closed,
        "review_only": True,
        "no_submit_by_design": True,
        "source_evidence_hash_summary": {
            "p9_live_read_only_canary_preparation": _summary(p9, name="p9_live_read_only_canary_preparation", hash_keys=("p9_live_read_only_canary_preparation_sha256",)),
            "approval_request": _summary(request, name="p10_live_canary_boundary_approval_request"),
            "order_intent": _summary(intent, name="p10_live_canary_one_order_intent"),
        },
        "validation": validation,
        "p9_live_canary_preparation_ready": validation["p9_live_canary_preparation_ready"],
        "live_canary_approval_packet_valid_review_only": validation["valid"],
        "live_canary_one_order_boundary_valid": validation["valid"],
        "live_canary_runtime_submit_action_created": False,
        "fresh_data_snapshot_confirmed": bool(intent.get("fresh_data_snapshot")) if intent else False,
        "research_signal_v2_created": bool(intent.get("research_signal_v2_created")) if intent else False,
        "signal_qa_passed": bool(intent.get("signal_qa_passed")) if intent else False,
        "hot_path_preorder_risk_gate_passed": bool(intent.get("hot_path_preorder_risk_gate_passed")) if intent else False,
        "hot_path_preorder_risk_gate_fresh": bool(intent.get("hot_path_preorder_risk_gate_fresh")) if intent else False,
        "max_live_canary_order_count": intent.get("max_order_count") if intent else None,
        "orders_already_submitted": intent.get("orders_already_submitted") if intent else None,
        "idempotency_key_present": _nonempty(intent.get("idempotency_key")) if intent else False,
        "duplicate_submit_lock_engaged": bool(intent.get("duplicate_submit_lock_engaged")) if intent else False,
        "post_submit_relock_planned": bool(intent.get("post_submit_relock_planned")) if intent else False,
        "post_submit_relock_confirmed": False,
        "live_canary_order_allowed_by_this_module": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        "actual_order_submission_performed": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "block_reasons": validation["block_reasons"],
        "warnings": validation["warnings"],
        "created_at_utc": utc_now_canonical(),
        **_disabled_payload(),
    }
    if validation["valid"]:
        report["p10_live_canary_one_order_execution_boundary_ready"] = True
        report["live_canary_approval_packet_valid_review_only"] = True
        report["live_canary_one_order_boundary_valid"] = True
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["p10_live_canary_one_order_execution_boundary_ready"] = False
        report["live_canary_approval_packet_valid_review_only"] = False
        report["live_canary_one_order_boundary_valid"] = False
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P10_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p10_live_canary_one_order_execution_boundary_id"] = stable_id("p10_live_canary_one_order_execution_boundary", report, 24)
    report["p10_live_canary_one_order_execution_boundary_sha256"] = sha256_json(report)
    return report


def build_valid_p10_fixture_sources() -> dict[str, Any]:
    # Use the P9 valid fixture source set to construct a P9-ready report without
    # depending on real live network calls or real API credentials.
    p9_sources = build_valid_p9_fixture_sources()
    from crypto_ai_system.execution.live_read_only_canary_preparation import build_p9_live_read_only_canary_preparation_report

    p9_report = build_p9_live_read_only_canary_preparation_report(**p9_sources)
    return {
        "p9_report": p9_report,
        "approval_request": LiveCanaryBoundaryApprovalRequest().to_dict(),
        "order_intent": LiveCanaryOneOrderIntent().to_dict(),
    }


def build_p10_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p10_fixture_sources()
    cases: dict[str, dict[str, Any]] = {
        "p9_not_ready": {"p9_report": {**valid["p9_report"], "status": "P9_WAITING", "live_canary_preparation_ready_for_manual_approval_packet": False}},
        "missing_approval_phrase": {"approval_request": {**valid["approval_request"], "exact_approval_phrase": ""}},
        "stale_data_snapshot": {"order_intent": {**valid["order_intent"], "fresh_data_snapshot": False, "data_snapshot_stale": True}},
        "signal_qa_failed": {"order_intent": {**valid["order_intent"], "signal_qa_passed": False}},
        "stale_hot_path_risk_gate": {"order_intent": {**valid["order_intent"], "hot_path_preorder_risk_gate_fresh": False}},
        "duplicate_idempotency": {"order_intent": {**valid["order_intent"], "idempotency_key_seen_before": True}},
        "max_order_count_gt_one": {"order_intent": {**valid["order_intent"], "max_order_count": 2}},
        "hard_cap_exceeded": {"order_intent": {**valid["order_intent"], "notional_usdt": 10.0}},
        "kill_switch_active": {"approval_request": {**valid["approval_request"], "manual_kill_switch_active": True}},
        "operator_requests_live_submit": {"approval_request": {**valid["approval_request"], "request_live_order_submission_enabled": True}},
        "live_order_endpoint_called": {"order_intent": {**valid["order_intent"], "live_order_endpoint_called": True}},
        "secret_leak": {"order_intent": {**valid["order_intent"], "secret_value_accessed": True}},
        "post_submit_relock_missing": {"order_intent": {**valid["order_intent"], "post_submit_relock_planned": False}},
        "live_scaled_enabled": {"p9_report": {**valid["p9_report"], "live_scaled_execution_enabled": True}},
    }
    results: dict[str, Any] = {}
    for name, patch in cases.items():
        sources = dict(valid)
        sources.update(patch)
        report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg, **sources)
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
            "actual_live_order_submitted": report["actual_live_order_submitted"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "artifact_type": "p10_live_canary_one_order_execution_boundary_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        "secret_value_accessed": False,
        **_disabled_payload(),
    }
    payload["p10_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p10_live_canary_one_order_execution_boundary(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p10_live_canary_one_order_execution_boundary_report(cfg=cfg)
    negative = build_p10_negative_fixture_results(cfg=cfg)
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p10_live_canary_one_order_execution_boundary")
    registry_record = append_registry_record(
        registry_path(cfg, P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_REGISTRY_NAME),
        {
            "artifact_type": "p10_live_canary_one_order_execution_boundary_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "p10_live_canary_one_order_execution_boundary_id": report["p10_live_canary_one_order_execution_boundary_id"],
            "p10_live_canary_one_order_execution_boundary_sha256": report["p10_live_canary_one_order_execution_boundary_sha256"],
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
            "actual_live_order_submitted": False,
            "secret_value_accessed": False,
            "created_at_utc": utc_now_canonical(),
        },
        registry_name=P10_LIVE_CANARY_ONE_ORDER_EXECUTION_BOUNDARY_REGISTRY_NAME,
        id_field="p10_live_canary_one_order_execution_boundary_registry_record_id",
        hash_field="p10_live_canary_one_order_execution_boundary_registry_record_sha256",
        id_prefix="p10_live_canary_one_order_execution_boundary_registry_record",
    )
    report["p10_live_canary_one_order_execution_boundary_registry_record_id"] = registry_record[
        "p10_live_canary_one_order_execution_boundary_registry_record_id"
    ]
    report["p10_live_canary_one_order_execution_boundary_registry_record_sha256"] = registry_record[
        "p10_live_canary_one_order_execution_boundary_registry_record_sha256"
    ]
    atomic_write_json(latest / "p10_live_canary_one_order_execution_boundary_report.json", report)
    atomic_write_json(latest / "p10_live_canary_one_order_execution_boundary_summary.json", {
        "status": report["status"],
        "blocked": report["blocked"],
        "p10_live_canary_one_order_execution_boundary_id": report["p10_live_canary_one_order_execution_boundary_id"],
        "p10_live_canary_one_order_execution_boundary_ready": report["p10_live_canary_one_order_execution_boundary_ready"],
        "live_canary_one_order_boundary_valid": report["live_canary_one_order_boundary_valid"],
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "secret_value_accessed": False,
        "block_reasons": report["block_reasons"],
        "warnings": report["warnings"],
    })
    atomic_write_json(latest / "p10_live_canary_one_order_execution_boundary_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p10_live_canary_one_order_execution_boundary_registry_record.json", registry_record)
    atomic_write_json(storage / "p10_live_canary_one_order_execution_boundary_report.json", report)
    return report


__all__ = [
    "EXACT_APPROVAL_PHRASE",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_READY_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "LiveCanaryBoundaryApprovalRequest",
    "LiveCanaryOneOrderIntent",
    "build_p10_live_canary_one_order_execution_boundary_report",
    "build_p10_negative_fixture_results",
    "build_valid_p10_fixture_sources",
    "persist_p10_live_canary_one_order_execution_boundary",
    "validate_p10_live_canary_one_order_execution_boundary",
]
