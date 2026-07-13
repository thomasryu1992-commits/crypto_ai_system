from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P13_LIVE_SCALED_READINESS_REVIEW_VERSION = "p13_live_scaled_readiness_review_v1"
P13_LIVE_SCALED_READINESS_REVIEW_REGISTRY_NAME = "p13_live_scaled_readiness_review_registry"

STATUS_WAITING_REVIEW_ONLY = "P13_LIVE_SCALED_READINESS_REVIEW_WAITING_REVIEW_ONLY"
STATUS_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY = "P13_LIVE_SCALED_READINESS_REVIEW_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P13_LIVE_SCALED_READINESS_REVIEW_BLOCKED_FAIL_CLOSED"

MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT = 25.0
MAX_DAILY_LOSS_CAP_USDT = 10.0
MAX_DAILY_ORDER_COUNT = 3
MAX_CONSECUTIVE_LOSS_COUNT = 2
MAX_OPEN_POSITION_COUNT = 1
MAX_LEVERAGE = 1.0
MAX_SLIPPAGE_BPS = 10.0
MAX_API_ERROR_RATE = 0.10
MAX_REJECTION_RATE = 0.20
MAX_RECONCILIATION_MISMATCH_COUNT = 0
MAX_MANUAL_OVERRIDE_COUNT = 0
MAX_INCIDENT_COUNT = 0
MAX_CRITICAL_ALERT_COUNT = 0

_REQUIRED_KILL_SWITCH_FLAGS = {
    "config_global_kill_switch_enforced",
    "operator_manual_kill_switch_enforced",
    "daily_loss_kill_switch_enforced",
    "consecutive_loss_kill_switch_enforced",
    "api_error_kill_switch_enforced",
    "reconciliation_mismatch_kill_switch_enforced",
    "stale_data_kill_switch_enforced",
    "missing_hard_required_source_kill_switch_enforced",
    "duplicate_submit_lock_enforced",
}

_REQUIRED_OPERATIONS_FLAGS = {
    "monitoring_alerting_ready",
    "rollback_ready",
    "full_shutdown_ready",
    "deployment_runbook_ready",
    "daily_report_ready",
    "incident_report_ready",
    "hot_path_preorder_risk_gate_required",
    "fresh_data_snapshot_required",
    "research_signal_v2_required",
    "signal_qa_required",
    "trading_decision_required",
    "idempotency_key_required",
    "post_submit_relock_required",
    "canonical_id_chain_required",
    "all_orders_must_reconcile",
}

_ALWAYS_DISABLED_FLAGS = {
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
    "mainnet_key_scope_allowed": False,
    "withdrawal_permission_allowed": False,
    "transfer_permission_allowed": False,
    "admin_permission_allowed": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
    "live_execution_unlock_authority": False,
    "live_trading_allowed_by_this_module": False,
    "live_order_submission_allowed": False,
    "live_order_submission_allowed_by_this_module": False,
    "live_scaled_readiness_allowed": False,
    "live_scaled_promotion_allowed": False,
    "live_scaled_promotion_allowed_by_this_module": False,
    "live_scaled_auto_trading_allowed": False,
    "limited_live_scaled_auto_trading_allowed": False,
    "live_scaled_approval_present": False,
    "separate_live_scaled_approval_present": False,
}


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _sha_from(payload: Mapping[str, Any], *keys: str) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in keys:
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_ALWAYS_DISABLED_FLAGS)
    payload.update(
        {
            "p13_live_scaled_readiness_review_started": False,
            "live_scaled_readiness_review_validated": False,
            "live_scaled_approval_packet_may_be_drafted": False,
            "separate_live_scaled_approval_required": True,
            "separate_live_scaled_approval_present": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "actual_live_order_submitted_by_this_module": False,
        }
    )
    return payload


@dataclass(frozen=True)
class LiveScaledControlPolicyEvidence:
    policy_id: str = "p13_limited_live_scaled_controls_v1"
    symbol_scope: tuple[str, ...] = ("BTCUSDT",)
    fixed_max_notional_usdt: float = 10.0
    daily_loss_cap_usdt: float = 5.0
    max_daily_order_count: int = 3
    max_consecutive_loss_count: int = 2
    max_open_position_count: int = 1
    max_leverage: float = 1.0
    max_slippage_bps: float = 8.0
    max_api_error_rate: float = 0.05
    max_rejection_rate: float = 0.10
    max_reconciliation_mismatch_count: int = 0
    max_manual_override_count: int = 0
    max_incident_count: int = 0
    max_critical_alert_count: int = 0
    config_global_kill_switch_enforced: bool = True
    operator_manual_kill_switch_enforced: bool = True
    daily_loss_kill_switch_enforced: bool = True
    consecutive_loss_kill_switch_enforced: bool = True
    api_error_kill_switch_enforced: bool = True
    reconciliation_mismatch_kill_switch_enforced: bool = True
    stale_data_kill_switch_enforced: bool = True
    missing_hard_required_source_kill_switch_enforced: bool = True
    duplicate_submit_lock_enforced: bool = True
    monitoring_alerting_ready: bool = True
    rollback_ready: bool = True
    full_shutdown_ready: bool = True
    deployment_runbook_ready: bool = True
    daily_report_ready: bool = True
    incident_report_ready: bool = True
    hot_path_preorder_risk_gate_required: bool = True
    fresh_data_snapshot_required: bool = True
    research_signal_v2_required: bool = True
    signal_qa_required: bool = True
    trading_decision_required: bool = True
    idempotency_key_required: bool = True
    post_submit_relock_required: bool = True
    canonical_id_chain_required: bool = True
    all_orders_must_reconcile: bool = True
    separate_live_scaled_approval_required: bool = True
    separate_live_scaled_approval_present: bool = False
    separate_live_scaled_approval_id: str | None = None
    live_scaled_execution_enabled: bool = False
    live_scaled_promotion_allowed: bool = False
    live_scaled_auto_trading_allowed: bool = False
    live_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False
    secret_value_accessed: bool = False
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    secret_file_accessed: bool = False
    secret_file_created: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False
    evidence_notes: tuple[str, ...] = field(default_factory=lambda: ("review_only_readiness_gate", "no_live_scaled_execution_permission"))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbol_scope"] = list(self.symbol_scope)
        payload["live_scaled_control_policy_evidence_sha256"] = sha256_json(payload)
        return payload


def build_default_live_scaled_control_policy_evidence() -> dict[str, Any]:
    return LiveScaledControlPolicyEvidence().to_dict()


def validate_live_scaled_control_policy_evidence(policy: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(policy or {})
    block_reasons: list[str] = []
    warning_reasons: list[str] = []

    symbols_raw = data.get("symbol_scope") or data.get("symbols_allowed") or []
    if isinstance(symbols_raw, str):
        symbols = [symbols_raw]
    else:
        symbols = [str(item) for item in symbols_raw if str(item).strip()]
    if symbols != ["BTCUSDT"]:
        block_reasons.append("P13_POLICY_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY")

    fixed_max_notional = _as_float(data.get("fixed_max_notional_usdt"), -1.0)
    daily_loss_cap = _as_float(data.get("daily_loss_cap_usdt"), -1.0)
    max_daily_orders = _as_int(data.get("max_daily_order_count"), -1)
    max_consecutive_losses = _as_int(data.get("max_consecutive_loss_count"), -1)
    max_open_positions = _as_int(data.get("max_open_position_count"), -1)
    max_leverage = _as_float(data.get("max_leverage"), -1.0)
    max_slippage = _as_float(data.get("max_slippage_bps"), -1.0)
    max_api_error_rate = _as_float(data.get("max_api_error_rate"), -1.0)
    max_rejection_rate = _as_float(data.get("max_rejection_rate"), -1.0)

    if fixed_max_notional <= 0 or fixed_max_notional > MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT:
        block_reasons.append("P13_POLICY_FIXED_MAX_NOTIONAL_OUT_OF_RANGE")
    if daily_loss_cap <= 0 or daily_loss_cap > MAX_DAILY_LOSS_CAP_USDT:
        block_reasons.append("P13_POLICY_DAILY_LOSS_CAP_OUT_OF_RANGE")
    if max_daily_orders <= 0 or max_daily_orders > MAX_DAILY_ORDER_COUNT:
        block_reasons.append("P13_POLICY_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE")
    if max_consecutive_losses <= 0 or max_consecutive_losses > MAX_CONSECUTIVE_LOSS_COUNT:
        block_reasons.append("P13_POLICY_MAX_CONSECUTIVE_LOSS_OUT_OF_RANGE")
    if max_open_positions <= 0 or max_open_positions > MAX_OPEN_POSITION_COUNT:
        block_reasons.append("P13_POLICY_MAX_OPEN_POSITION_COUNT_OUT_OF_RANGE")
    if max_leverage <= 0 or max_leverage > MAX_LEVERAGE:
        block_reasons.append("P13_POLICY_MAX_LEVERAGE_OUT_OF_RANGE")
    if max_slippage < 0 or max_slippage > MAX_SLIPPAGE_BPS:
        block_reasons.append("P13_POLICY_MAX_SLIPPAGE_OUT_OF_RANGE")
    if max_api_error_rate < 0 or max_api_error_rate > MAX_API_ERROR_RATE:
        block_reasons.append("P13_POLICY_MAX_API_ERROR_RATE_OUT_OF_RANGE")
    if max_rejection_rate < 0 or max_rejection_rate > MAX_REJECTION_RATE:
        block_reasons.append("P13_POLICY_MAX_REJECTION_RATE_OUT_OF_RANGE")
    if _as_int(data.get("max_reconciliation_mismatch_count"), -1) != MAX_RECONCILIATION_MISMATCH_COUNT:
        block_reasons.append("P13_POLICY_RECONCILIATION_MISMATCH_CAP_NOT_ZERO")
    if _as_int(data.get("max_manual_override_count"), -1) != MAX_MANUAL_OVERRIDE_COUNT:
        block_reasons.append("P13_POLICY_MANUAL_OVERRIDE_CAP_NOT_ZERO")
    if _as_int(data.get("max_incident_count"), -1) != MAX_INCIDENT_COUNT:
        block_reasons.append("P13_POLICY_INCIDENT_CAP_NOT_ZERO")
    if _as_int(data.get("max_critical_alert_count"), -1) != MAX_CRITICAL_ALERT_COUNT:
        block_reasons.append("P13_POLICY_CRITICAL_ALERT_CAP_NOT_ZERO")

    for key in sorted(_REQUIRED_KILL_SWITCH_FLAGS):
        if not _bool(data.get(key)):
            block_reasons.append(f"P13_POLICY_REQUIRED_KILL_SWITCH_MISSING:{key}")
    for key in sorted(_REQUIRED_OPERATIONS_FLAGS):
        if not _bool(data.get(key)):
            block_reasons.append(f"P13_POLICY_REQUIRED_OPERATIONAL_CONTROL_MISSING:{key}")

    if not _bool(data.get("separate_live_scaled_approval_required")):
        block_reasons.append("P13_POLICY_SEPARATE_LIVE_SCALED_APPROVAL_NOT_REQUIRED")
    if _bool(data.get("separate_live_scaled_approval_present")) or _nonempty(data.get("separate_live_scaled_approval_id")):
        warning_reasons.append("P13_POLICY_SEPARATE_APPROVAL_PRESENT_FOR_NEXT_STAGE_ONLY")

    unsafe_false_fields = [
        "live_scaled_execution_enabled",
        "live_scaled_promotion_allowed",
        "live_scaled_auto_trading_allowed",
        "live_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
        "secret_value_accessed",
        "secret_value_logged",
        "api_key_value_logged",
        "api_secret_value_logged",
        "secret_file_accessed",
        "secret_file_created",
        "withdrawal_permission_allowed",
        "transfer_permission_allowed",
        "admin_permission_allowed",
    ]
    for field_name in unsafe_false_fields:
        if _bool(data.get(field_name)):
            block_reasons.append(f"P13_POLICY_UNSAFE_FLAG_TRUE:{field_name}")

    valid = not block_reasons
    result = {
        "live_scaled_control_policy_valid": valid,
        "blocked": not valid,
        "block_reasons": sorted(set(block_reasons)),
        "warning_reasons": sorted(set(warning_reasons)),
        "symbol_scope": symbols,
        "fixed_max_notional_usdt": fixed_max_notional,
        "daily_loss_cap_usdt": daily_loss_cap,
        "max_daily_order_count": max_daily_orders,
        "max_consecutive_loss_count": max_consecutive_losses,
        "max_open_position_count": max_open_positions,
        "max_leverage": max_leverage,
        "max_slippage_bps": max_slippage,
        "max_api_error_rate": max_api_error_rate,
        "max_rejection_rate": max_rejection_rate,
        "separate_live_scaled_approval_required": _bool(data.get("separate_live_scaled_approval_required")),
        "separate_live_scaled_approval_present": _bool(data.get("separate_live_scaled_approval_present")),
        "live_scaled_execution_enabled": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_auto_trading_allowed": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    result["live_scaled_control_policy_validation_sha256"] = sha256_json(result)
    return result


def _validate_p12_source(p12_report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(p12_report or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []

    if not data:
        waiting_reasons.append("P13_SOURCE_P12_REPORT_MISSING")
    elif not _bool(data.get("repeated_clean_live_canary_sessions_validated")):
        waiting_reasons.append("P13_SOURCE_P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_NOT_VALIDATED")
    else:
        if not _bool(data.get("live_scaled_readiness_candidate_evidence_created")):
            block_reasons.append("P13_SOURCE_P12_READINESS_CANDIDATE_EVIDENCE_MISSING")
        if _as_int(data.get("reconciliation_mismatch_count"), 0) > MAX_RECONCILIATION_MISMATCH_COUNT:
            block_reasons.append("P13_SOURCE_P12_RECONCILIATION_MISMATCH_NONZERO")
        if _as_int(data.get("manual_override_count"), 0) > MAX_MANUAL_OVERRIDE_COUNT:
            block_reasons.append("P13_SOURCE_P12_MANUAL_OVERRIDE_NONZERO")
        if _as_int(data.get("incident_count"), 0) > MAX_INCIDENT_COUNT:
            block_reasons.append("P13_SOURCE_P12_INCIDENT_NONZERO")
        if _as_int(data.get("critical_alert_count"), 0) > MAX_CRITICAL_ALERT_COUNT:
            block_reasons.append("P13_SOURCE_P12_CRITICAL_ALERT_NONZERO")
        if _as_float(data.get("average_abs_slippage_bps"), 0.0) > MAX_SLIPPAGE_BPS:
            block_reasons.append("P13_SOURCE_P12_AVERAGE_SLIPPAGE_ABOVE_THRESHOLD")
        if _as_float(data.get("api_error_rate"), 0.0) > MAX_API_ERROR_RATE:
            block_reasons.append("P13_SOURCE_P12_API_ERROR_RATE_ABOVE_THRESHOLD")
        if _as_float(data.get("rejection_rate"), 0.0) > MAX_REJECTION_RATE:
            block_reasons.append("P13_SOURCE_P12_REJECTION_RATE_ABOVE_THRESHOLD")

    unsafe_fields = [
        "secret_value_accessed",
        "secret_value_logged",
        "api_key_value_logged",
        "api_secret_value_logged",
        "secret_file_accessed",
        "secret_file_created",
        "live_scaled_readiness_allowed",
        "live_scaled_promotion_allowed",
        "live_scaled_execution_enabled",
        "live_scaled_auto_trading_allowed",
        "limited_live_scaled_auto_trading_allowed",
        "live_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
        "mainnet_key_scope_allowed",
        "withdrawal_permission_allowed",
        "transfer_permission_allowed",
        "admin_permission_allowed",
    ]
    for field_name in unsafe_fields:
        if _bool(data.get(field_name)):
            block_reasons.append(f"P13_SOURCE_P12_UNSAFE_FLAG_TRUE:{field_name}")

    return {
        "p12_source_present": bool(data),
        "p12_source_waiting": bool(waiting_reasons),
        "p12_source_blocked": bool(block_reasons),
        "p12_source_waiting_reasons": sorted(set(waiting_reasons)),
        "p12_source_block_reasons": sorted(set(block_reasons)),
        "p12_repeated_clean_live_canary_sessions_validated": _bool(data.get("repeated_clean_live_canary_sessions_validated")),
        "p12_live_scaled_readiness_candidate_evidence_created": _bool(data.get("live_scaled_readiness_candidate_evidence_created")),
        "p12_report_sha256": _sha_from(data, "p12_repeated_clean_live_canary_sessions_sha256", "p12_repeated_clean_live_canary_sessions_report_sha256"),
    }


def build_live_scaled_readiness_review_report(
    *,
    cfg: AppConfig | None = None,
    p12_report: Mapping[str, Any] | None = None,
    control_policy_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if cfg is not None:
        if p12_report is None:
            p12_report = _read_latest_json(cfg, "p12_repeated_clean_live_canary_sessions_report.json")
        if control_policy_evidence is None:
            control_policy_evidence = _read_latest_json(cfg, "p13_live_scaled_control_policy_evidence.json")
    p12 = dict(p12_report or {})
    control = dict(control_policy_evidence or {})

    p12_validation = _validate_p12_source(p12)
    block_reasons = list(p12_validation["p12_source_block_reasons"])
    waiting_reasons = list(p12_validation["p12_source_waiting_reasons"])
    policy_validation: dict[str, Any]

    if not control and not waiting_reasons:
        waiting_reasons.append("P13_CONTROL_POLICY_EVIDENCE_MISSING")
        policy_validation = validate_live_scaled_control_policy_evidence({})
    elif control:
        policy_validation = validate_live_scaled_control_policy_evidence(control)
        block_reasons.extend(policy_validation["block_reasons"])
    else:
        policy_validation = validate_live_scaled_control_policy_evidence({})

    blocked = bool(block_reasons)
    waiting = bool(waiting_reasons) and not blocked
    ready_for_separate_approval = not blocked and not waiting
    status = (
        STATUS_BLOCKED_FAIL_CLOSED
        if blocked
        else (STATUS_WAITING_REVIEW_ONLY if waiting else STATUS_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY)
    )

    disabled = _disabled_payload()
    report_id_source = {
        "p12_report_sha256": p12_validation.get("p12_report_sha256"),
        "policy_sha256": control.get("live_scaled_control_policy_evidence_sha256") or sha256_json(control) if control else None,
        "status": status,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
    }
    report = {
        "version": P13_LIVE_SCALED_READINESS_REVIEW_VERSION,
        "p13_live_scaled_readiness_review_id": stable_id("p13_live_scaled_readiness_review", report_id_source, 24),
        "status": status,
        "review_only": True,
        "blocked": blocked,
        "waiting": waiting,
        "ready_for_separate_live_scaled_approval_review_only": ready_for_separate_approval,
        "p12_source_validation": p12_validation,
        "live_scaled_control_policy_validation": policy_validation,
        "p12_report_sha256": p12_validation.get("p12_report_sha256"),
        "live_scaled_control_policy_evidence_sha256": control.get("live_scaled_control_policy_evidence_sha256") if control else None,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "warning_reasons": sorted(set(policy_validation.get("warning_reasons") or [])),
        "readiness_controls": {
            "symbol_scope": policy_validation.get("symbol_scope", []),
            "fixed_max_notional_usdt": policy_validation.get("fixed_max_notional_usdt"),
            "daily_loss_cap_usdt": policy_validation.get("daily_loss_cap_usdt"),
            "max_daily_order_count": policy_validation.get("max_daily_order_count"),
            "max_consecutive_loss_count": policy_validation.get("max_consecutive_loss_count"),
            "max_open_position_count": policy_validation.get("max_open_position_count"),
            "max_leverage": policy_validation.get("max_leverage"),
            "max_slippage_bps": policy_validation.get("max_slippage_bps"),
            "max_api_error_rate": policy_validation.get("max_api_error_rate"),
            "max_rejection_rate": policy_validation.get("max_rejection_rate"),
        },
        "kill_switch_controls_required": sorted(_REQUIRED_KILL_SWITCH_FLAGS),
        "operational_controls_required": sorted(_REQUIRED_OPERATIONS_FLAGS),
        "live_scaled_approval_packet_may_be_drafted": ready_for_separate_approval,
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "separate_live_scaled_approval_valid": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_scaled_auto_trading_allowed": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "actual_live_order_submitted_by_this_module": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    report.update(disabled)
    # Preserve review-stage flags after the disabled baseline overlay.
    report.update(
        {
            "status": status,
            "blocked": blocked,
            "waiting": waiting,
            "ready_for_separate_live_scaled_approval_review_only": ready_for_separate_approval,
            "live_scaled_approval_packet_may_be_drafted": ready_for_separate_approval,
            "separate_live_scaled_approval_required": True,
            "separate_live_scaled_approval_present": False,
            "separate_live_scaled_approval_valid": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "live_scaled_readiness_allowed": False,
            "live_scaled_promotion_allowed": False,
            "live_scaled_execution_enabled": False,
            "live_scaled_auto_trading_allowed": False,
            "live_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "secret_value_accessed": False,
        }
    )
    unsafe_truthy = truthy_execution_flags(report)
    report["unsafe_truthy_execution_flags"] = unsafe_truthy
    if unsafe_truthy and "P13_TRUTHY_EXECUTION_FLAG_DETECTED" not in report["block_reasons"]:
        report["block_reasons"] = sorted(set(report["block_reasons"] + ["P13_TRUTHY_EXECUTION_FLAG_DETECTED"]))
        report["blocked"] = True
        report["waiting"] = False
        report["ready_for_separate_live_scaled_approval_review_only"] = False
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["live_scaled_approval_packet_may_be_drafted"] = False
    report["p13_live_scaled_readiness_review_sha256"] = sha256_json(
        {k: v for k, v in report.items() if k not in {"created_at_utc", "p13_live_scaled_readiness_review_sha256"}}
    )
    return report


def build_p13_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    valid_p12 = {
        "status": "P12_REPEATED_CLEAN_LIVE_CANARY_SESSIONS_VALIDATED_REVIEW_ONLY",
        "p12_repeated_clean_live_canary_sessions_sha256": "c" * 64,
        "repeated_live_canary_session_evidence_present": True,
        "repeated_clean_live_canary_sessions_validated": True,
        "live_scaled_readiness_candidate_evidence_created": True,
        "reconciliation_mismatch_count": 0,
        "manual_override_count": 0,
        "incident_count": 0,
        "critical_alert_count": 0,
        "average_abs_slippage_bps": 1.0,
        "api_error_rate": 0.0,
        "rejection_rate": 0.0,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
    }
    valid_policy = build_default_live_scaled_control_policy_evidence()
    fixtures: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
        "p12_not_validated": ({**valid_p12, "repeated_clean_live_canary_sessions_validated": False}, valid_policy),
        "missing_fixed_notional_cap": (valid_p12, {**valid_policy, "fixed_max_notional_usdt": 0}),
        "notional_cap_too_high": (valid_p12, {**valid_policy, "fixed_max_notional_usdt": 1000}),
        "daily_loss_cap_too_high": (valid_p12, {**valid_policy, "daily_loss_cap_usdt": 100}),
        "max_daily_order_count_too_high": (valid_p12, {**valid_policy, "max_daily_order_count": 100}),
        "max_leverage_too_high": (valid_p12, {**valid_policy, "max_leverage": 5}),
        "kill_switch_missing": (valid_p12, {**valid_policy, "operator_manual_kill_switch_enforced": False}),
        "rollback_missing": (valid_p12, {**valid_policy, "rollback_ready": False}),
        "daily_report_missing": (valid_p12, {**valid_policy, "daily_report_ready": False}),
        "incident_report_missing": (valid_p12, {**valid_policy, "incident_report_ready": False}),
        "secret_leak": (valid_p12, {**valid_policy, "secret_value_logged": True}),
        "live_scaled_enabled": (valid_p12, {**valid_policy, "live_scaled_execution_enabled": True}),
        "live_order_allowed": (valid_p12, {**valid_policy, "live_order_submission_allowed": True}),
        "withdrawal_permission_allowed": (valid_p12, {**valid_policy, "withdrawal_permission_allowed": True}),
        "runtime_mutation": (valid_p12, {**valid_policy, "runtime_settings_mutated": True}),
    }
    results: dict[str, Any] = {}
    for name, (p12, policy) in fixtures.items():
        report = build_live_scaled_readiness_review_report(cfg=cfg, p12_report=p12, control_policy_evidence=policy)
        results[name] = {
            "status": report["status"],
            "blocked_fail_closed": report["status"] == STATUS_BLOCKED_FAIL_CLOSED or bool(report["block_reasons"]) or bool(report["waiting_reasons"]),
            "waiting": report["waiting"],
            "ready_for_separate_live_scaled_approval_review_only": report["ready_for_separate_live_scaled_approval_review_only"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "version": P13_LIVE_SCALED_READINESS_REVIEW_VERSION,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "live_scaled_readiness_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload["p13_live_scaled_readiness_review_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_live_scaled_readiness_review_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report)
    record = {
        "version": P13_LIVE_SCALED_READINESS_REVIEW_VERSION,
        "p13_live_scaled_readiness_review_id": data.get("p13_live_scaled_readiness_review_id"),
        "p13_live_scaled_readiness_review_sha256": data.get("p13_live_scaled_readiness_review_sha256"),
        "status": data.get("status"),
        "review_only": True,
        "blocked": data.get("blocked"),
        "waiting": data.get("waiting"),
        "ready_for_separate_live_scaled_approval_review_only": data.get("ready_for_separate_live_scaled_approval_review_only"),
        "p12_report_sha256": data.get("p12_report_sha256"),
        "live_scaled_control_policy_evidence_sha256": data.get("live_scaled_control_policy_evidence_sha256"),
        "block_reasons": list(data.get("block_reasons") or []),
        "waiting_reasons": list(data.get("waiting_reasons") or []),
        "live_scaled_approval_packet_may_be_drafted": data.get("live_scaled_approval_packet_may_be_drafted"),
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_promotion_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "runtime_settings_mutated": False,
        "created_at_utc": data.get("created_at_utc") or utc_now_canonical(),
    }
    record["p13_live_scaled_readiness_review_registry_record_id"] = stable_id("p13_live_scaled_readiness_review_registry", record, 24)
    record["p13_live_scaled_readiness_review_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_scaled_readiness_review(
    *,
    cfg: AppConfig | None = None,
    p12_report: Mapping[str, Any] | None = None,
    control_policy_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    if control_policy_evidence is None:
        existing = _read_latest_json(cfg, "p13_live_scaled_control_policy_evidence.json")
        control_policy_evidence = existing if existing else build_default_live_scaled_control_policy_evidence()
    report = build_live_scaled_readiness_review_report(
        cfg=cfg,
        p12_report=p12_report,
        control_policy_evidence=control_policy_evidence,
    )
    latest = _latest_dir(cfg)
    out_dir = _storage_dir(cfg, "storage/p13_live_scaled_readiness_review")
    registry_record = build_live_scaled_readiness_review_registry_record(report)
    persisted = append_registry_record(
        registry_path(cfg, P13_LIVE_SCALED_READINESS_REVIEW_REGISTRY_NAME),
        registry_record,
        registry_name=P13_LIVE_SCALED_READINESS_REVIEW_REGISTRY_NAME,
        id_field="p13_live_scaled_readiness_review_registry_record_id",
        hash_field="p13_live_scaled_readiness_review_registry_record_sha256",
        id_prefix="p13_live_scaled_readiness_review_registry",
    )
    summary = {
        "version": P13_LIVE_SCALED_READINESS_REVIEW_VERSION,
        "status": report.get("status"),
        "review_only": True,
        "blocked": report.get("blocked"),
        "waiting": report.get("waiting"),
        "ready_for_separate_live_scaled_approval_review_only": report.get("ready_for_separate_live_scaled_approval_review_only"),
        "live_scaled_approval_packet_may_be_drafted": report.get("live_scaled_approval_packet_may_be_drafted"),
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "block_reasons": list(report.get("block_reasons") or []),
        "waiting_reasons": list(report.get("waiting_reasons") or []),
        "p13_live_scaled_readiness_review_sha256": report.get("p13_live_scaled_readiness_review_sha256"),
        "created_at_utc": utc_now_canonical(),
    }
    negative = build_p13_negative_fixture_results(cfg=cfg)
    atomic_write_json(latest / "p13_live_scaled_readiness_review_report.json", {**report, **persisted})
    atomic_write_json(latest / "p13_live_scaled_readiness_review_summary.json", summary)
    atomic_write_json(latest / "p13_live_scaled_readiness_review_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p13_live_scaled_readiness_review_registry_record.json", persisted)
    atomic_write_json(out_dir / "p13_live_scaled_readiness_review_report.json", {**report, **persisted})
    if control_policy_evidence:
        atomic_write_json(latest / "p13_live_scaled_control_policy_evidence.json", dict(control_policy_evidence))
    return {**report, **persisted}


__all__ = [
    "P13_LIVE_SCALED_READINESS_REVIEW_VERSION",
    "P13_LIVE_SCALED_READINESS_REVIEW_REGISTRY_NAME",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT",
    "LiveScaledControlPolicyEvidence",
    "build_default_live_scaled_control_policy_evidence",
    "validate_live_scaled_control_policy_evidence",
    "build_live_scaled_readiness_review_report",
    "build_p13_negative_fixture_results",
    "persist_live_scaled_readiness_review",
]
