from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.live_scaled_readiness_review import (
    MAX_API_ERROR_RATE,
    MAX_DAILY_LOSS_CAP_USDT,
    MAX_DAILY_ORDER_COUNT,
    MAX_LEVERAGE,
    MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT,
    MAX_OPEN_POSITION_COUNT,
    MAX_REJECTION_RATE,
    MAX_SLIPPAGE_BPS,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_VERSION = "p15_limited_live_scaled_runtime_enablement_boundary_v1"
P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_REGISTRY_NAME = "p15_limited_live_scaled_runtime_enablement_boundary_registry"

STATUS_WAITING_REVIEW_ONLY = "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY_NO_EXECUTION = "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_VALID_REVIEW_ONLY_NO_EXECUTION"
STATUS_BLOCKED_FAIL_CLOSED = "P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_BOUNDARY_BLOCKED_FAIL_CLOSED"

LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE = (
    "I APPROVE LIMITED LIVE SCALED RUNTIME BOUNDARY REVIEW ONLY - NO ORDER SUBMISSION"
)

_REQUIRED_REQUEST_ACKS = {
    "acknowledged_btcusdt_only",
    "acknowledged_fixed_max_notional_cap",
    "acknowledged_daily_loss_cap",
    "acknowledged_max_daily_order_count",
    "acknowledged_max_consecutive_loss_cap",
    "acknowledged_max_open_position_count",
    "acknowledged_max_leverage_cap",
    "acknowledged_max_slippage_cap",
    "acknowledged_max_api_error_rate_cap",
    "acknowledged_kill_switches",
    "acknowledged_fresh_data_signal_risk_refresh",
    "acknowledged_idempotency_and_duplicate_submit_lock",
    "acknowledged_post_submit_relock",
    "acknowledged_reconciliation_required",
    "acknowledged_daily_report_required",
    "acknowledged_incident_report_required",
    "acknowledged_rollback_and_full_shutdown",
    "acknowledged_no_secret_value_logging",
    "acknowledged_no_runtime_mutation_by_boundary",
    "acknowledged_separate_operator_runtime_process_required",
}

_REQUIRED_POLICY_FLAGS = {
    "requires_current_stage_policy_load",
    "requires_fresh_market_data",
    "requires_source_qa",
    "requires_data_snapshot_feature_lineage",
    "requires_research_signal_v2",
    "requires_signal_qa",
    "requires_trading_decision",
    "requires_hot_path_preorder_risk_gate",
    "requires_order_intent_after_risk_gate",
    "requires_duplicate_submit_lock",
    "requires_idempotency_key",
    "requires_exchange_submit_evidence",
    "requires_post_submit_relock",
    "requires_status_polling",
    "requires_reconciliation",
    "requires_outcome_feedback",
    "requires_daily_report",
    "requires_incident_report",
    "requires_monitoring_alerting",
    "requires_rollback_full_shutdown",
    "requires_canonical_id_chain",
    "requires_all_orders_reconciled",
}

_REQUIRED_LOOP_FLAGS = {
    "scheduler_tick_defined",
    "current_stage_policy_loaded_required",
    "fresh_market_data_required",
    "source_qa_required",
    "data_snapshot_required",
    "feature_lineage_required",
    "research_signal_v2_required",
    "signal_qa_required",
    "trading_decision_required",
    "hot_path_preorder_risk_gate_required",
    "order_intent_after_risk_gate_required",
    "duplicate_submit_lock_required",
    "idempotency_key_required",
    "post_submit_relock_required",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_full_shutdown_required",
    "canonical_id_chain_required",
    "all_orders_must_reconcile",
    "kill_switch_global_required",
    "kill_switch_manual_required",
    "kill_switch_daily_loss_required",
    "kill_switch_consecutive_loss_required",
    "kill_switch_api_error_required",
    "kill_switch_reconciliation_mismatch_required",
    "kill_switch_stale_data_required",
    "kill_switch_missing_required_source_required",
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
    "limited_live_scaled_auto_trading_allowed_by_this_module": False,
    "live_scaled_runtime_enablement_allowed": False,
    "live_scaled_runtime_enablement_performed": False,
    "runtime_scheduler_enabled": False,
    "runtime_loop_started": False,
    "actual_live_order_submitted": False,
    "actual_live_order_submitted_by_this_module": False,
    "live_order_endpoint_called": False,
    "order_endpoint_called": False,
    "order_status_endpoint_called": False,
    "cancel_endpoint_called": False,
    "http_request_sent": False,
    "signature_created": False,
    "signed_request_created": False,
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


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


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
            "p15_limited_live_scaled_runtime_enablement_boundary_started": False,
            "p15_limited_live_scaled_runtime_boundary_valid_review_only": False,
            "runtime_stage_policy_valid_review_only": False,
            "runtime_loop_controls_valid_review_only": False,
            "operator_runtime_enablement_request_valid_review_only": False,
            "limited_live_scaled_runtime_boundary_ready_review_only": False,
        }
    )
    return payload


@dataclass(frozen=True)
class LimitedLiveScaledRuntimeEnablementRequest:
    runtime_enablement_request_id: str = "p15_limited_live_scaled_runtime_enablement_request_review_only"
    source_p14_live_scaled_approval_intake_validation_sha256: str = field(default_factory=lambda: "f" * 64)
    requested_stage: str = "limited_live_scaled"
    operator_id: str = "operator_thomas_manual_runtime_review"
    ticket_or_signature: str = field(default_factory=lambda: f"LIVE-SCALED-RUNTIME-{stable_id('ticket', {'phase': 15}, 8)}")
    enablement_phrase: str = LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE
    human_operator_submitted: bool = True
    auto_generated_enablement_file: bool = False
    canonical_utc_timestamp: str = field(default_factory=utc_now_canonical)
    acknowledged_btcusdt_only: bool = True
    acknowledged_fixed_max_notional_cap: bool = True
    acknowledged_daily_loss_cap: bool = True
    acknowledged_max_daily_order_count: bool = True
    acknowledged_max_consecutive_loss_cap: bool = True
    acknowledged_max_open_position_count: bool = True
    acknowledged_max_leverage_cap: bool = True
    acknowledged_max_slippage_cap: bool = True
    acknowledged_max_api_error_rate_cap: bool = True
    acknowledged_kill_switches: bool = True
    acknowledged_fresh_data_signal_risk_refresh: bool = True
    acknowledged_idempotency_and_duplicate_submit_lock: bool = True
    acknowledged_post_submit_relock: bool = True
    acknowledged_reconciliation_required: bool = True
    acknowledged_daily_report_required: bool = True
    acknowledged_incident_report_required: bool = True
    acknowledged_rollback_and_full_shutdown: bool = True
    acknowledged_no_secret_value_logging: bool = True
    acknowledged_no_runtime_mutation_by_boundary: bool = True
    acknowledged_separate_operator_runtime_process_required: bool = True
    requests_runtime_scheduler_enabled: bool = False
    requests_runtime_loop_started: bool = False
    requests_live_scaled_execution_enabled: bool = False
    requests_live_order_submission_allowed: bool = False
    requests_place_order_enabled: bool = False
    requests_cancel_order_enabled: bool = False
    requests_auto_promotion_allowed: bool = False
    requests_runtime_settings_mutation: bool = False
    requests_score_weight_mutation: bool = False
    secret_value_accessed: bool = False
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False
    withdrawal_permission_requested: bool = False
    transfer_permission_requested: bool = False
    admin_permission_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime_enablement_request_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LimitedLiveScaledRuntimeStagePolicy:
    runtime_stage_policy_id: str = "p15_limited_live_scaled_runtime_stage_policy_review_only"
    source_p14_live_scaled_approval_intake_validation_sha256: str = field(default_factory=lambda: "f" * 64)
    stage: str = "limited_live_scaled"
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
    requires_current_stage_policy_load: bool = True
    requires_fresh_market_data: bool = True
    requires_source_qa: bool = True
    requires_data_snapshot_feature_lineage: bool = True
    requires_research_signal_v2: bool = True
    requires_signal_qa: bool = True
    requires_trading_decision: bool = True
    requires_hot_path_preorder_risk_gate: bool = True
    requires_order_intent_after_risk_gate: bool = True
    requires_duplicate_submit_lock: bool = True
    requires_idempotency_key: bool = True
    requires_exchange_submit_evidence: bool = True
    requires_post_submit_relock: bool = True
    requires_status_polling: bool = True
    requires_reconciliation: bool = True
    requires_outcome_feedback: bool = True
    requires_daily_report: bool = True
    requires_incident_report: bool = True
    requires_monitoring_alerting: bool = True
    requires_rollback_full_shutdown: bool = True
    requires_canonical_id_chain: bool = True
    requires_all_orders_reconciled: bool = True
    generated_for_review_only: bool = True
    runtime_scheduler_enabled: bool = False
    runtime_loop_started: bool = False
    live_scaled_execution_enabled: bool = False
    live_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    secret_value_accessed: bool = False
    withdrawal_permission_allowed: bool = False
    transfer_permission_allowed: bool = False
    admin_permission_allowed: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["symbol_scope"] = list(self.symbol_scope)
        payload["runtime_stage_policy_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LimitedLiveScaledRuntimeLoopControls:
    runtime_loop_controls_id: str = "p15_limited_live_scaled_runtime_loop_controls_review_only"
    scheduler_tick_defined: bool = True
    scheduler_interval_seconds: int = 60
    current_stage_policy_loaded_required: bool = True
    fresh_market_data_required: bool = True
    source_qa_required: bool = True
    data_snapshot_required: bool = True
    feature_lineage_required: bool = True
    research_signal_v2_required: bool = True
    signal_qa_required: bool = True
    trading_decision_required: bool = True
    hot_path_preorder_risk_gate_required: bool = True
    order_intent_after_risk_gate_required: bool = True
    duplicate_submit_lock_required: bool = True
    idempotency_key_required: bool = True
    post_submit_relock_required: bool = True
    status_polling_required: bool = True
    reconciliation_required: bool = True
    outcome_feedback_required: bool = True
    daily_report_required: bool = True
    incident_report_required: bool = True
    monitoring_alerting_required: bool = True
    rollback_full_shutdown_required: bool = True
    canonical_id_chain_required: bool = True
    all_orders_must_reconcile: bool = True
    kill_switch_global_required: bool = True
    kill_switch_manual_required: bool = True
    kill_switch_daily_loss_required: bool = True
    kill_switch_consecutive_loss_required: bool = True
    kill_switch_api_error_required: bool = True
    kill_switch_reconciliation_mismatch_required: bool = True
    kill_switch_stale_data_required: bool = True
    kill_switch_missing_required_source_required: bool = True
    runtime_scheduler_enabled: bool = False
    runtime_loop_started: bool = False
    live_order_endpoint_called: bool = False
    order_endpoint_called: bool = False
    http_request_sent: bool = False
    signature_created: bool = False
    signed_request_created: bool = False
    live_scaled_execution_enabled: bool = False
    live_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    auto_promotion_allowed: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    secret_value_accessed: bool = False
    secret_value_logged: bool = False
    api_key_value_logged: bool = False
    api_secret_value_logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime_loop_controls_sha256"] = sha256_json(payload)
        return payload


def build_review_only_runtime_stage_policy(p14_report: Mapping[str, Any]) -> dict[str, Any]:
    p14_sha = _sha_from(p14_report, "p14_live_scaled_approval_intake_validation_sha256") or "f" * 64
    return LimitedLiveScaledRuntimeStagePolicy(source_p14_live_scaled_approval_intake_validation_sha256=p14_sha).to_dict()


def build_valid_runtime_enablement_request(p14_report: Mapping[str, Any]) -> dict[str, Any]:
    p14_sha = _sha_from(p14_report, "p14_live_scaled_approval_intake_validation_sha256") or "f" * 64
    return LimitedLiveScaledRuntimeEnablementRequest(source_p14_live_scaled_approval_intake_validation_sha256=p14_sha).to_dict()


def build_review_only_runtime_loop_controls() -> dict[str, Any]:
    return LimitedLiveScaledRuntimeLoopControls().to_dict()


def _validate_p14_source(p14_report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(p14_report or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P15_SOURCE_P14_REPORT_MISSING")
    elif not _bool(data.get("live_scaled_approval_valid_review_only")):
        waiting_reasons.append("P15_SOURCE_P14_LIVE_SCALED_APPROVAL_NOT_VALID")
    else:
        if not _bool(data.get("live_scaled_approval_packet_valid")):
            block_reasons.append("P15_SOURCE_P14_APPROVAL_PACKET_NOT_VALID")
        if not _bool(data.get("live_scaled_approval_intake_valid")):
            block_reasons.append("P15_SOURCE_P14_APPROVAL_INTAKE_NOT_VALID")
        if not _bool(data.get("separate_runtime_enablement_step_required")):
            block_reasons.append("P15_SOURCE_P14_SEPARATE_RUNTIME_ENABLEMENT_NOT_REQUIRED")
    unsafe_fields = [
        "limited_live_scaled_auto_trading_allowed",
        "live_scaled_runtime_enablement_allowed",
        "live_scaled_execution_enabled",
        "live_scaled_promotion_allowed",
        "live_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "runtime_scheduler_enabled",
        "runtime_loop_started",
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
    for field_name in unsafe_fields:
        if _bool(data.get(field_name)):
            block_reasons.append(f"P15_SOURCE_P14_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "p14_source_present": bool(data),
        "p14_source_waiting": bool(waiting_reasons),
        "p14_source_blocked": bool(block_reasons),
        "p14_source_waiting_reasons": sorted(set(waiting_reasons)),
        "p14_source_block_reasons": sorted(set(block_reasons)),
        "p14_live_scaled_approval_valid_review_only": _bool(data.get("live_scaled_approval_valid_review_only")),
        "p14_live_scaled_approval_packet_valid": _bool(data.get("live_scaled_approval_packet_valid")),
        "p14_live_scaled_approval_intake_valid": _bool(data.get("live_scaled_approval_intake_valid")),
        "p14_separate_runtime_enablement_step_required": _bool(data.get("separate_runtime_enablement_step_required")),
        "p14_report_sha256": _sha_from(data, "p14_live_scaled_approval_intake_validation_sha256"),
    }


def _validate_enablement_request(request: Mapping[str, Any], p14_validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(request or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P15_RUNTIME_ENABLEMENT_REQUEST_MISSING")
    else:
        if str(data.get("requested_stage") or "") != "limited_live_scaled":
            block_reasons.append("P15_REQUEST_STAGE_INVALID")
        if not _nonempty(data.get("runtime_enablement_request_id")):
            block_reasons.append("P15_REQUEST_ID_MISSING")
        p14_sha = p14_validation.get("p14_report_sha256")
        if p14_sha and data.get("source_p14_live_scaled_approval_intake_validation_sha256") != p14_sha:
            block_reasons.append("P15_REQUEST_P14_HASH_MISMATCH")
        if not _nonempty(data.get("operator_id")):
            block_reasons.append("P15_REQUEST_OPERATOR_ID_MISSING")
        if not _nonempty(data.get("ticket_or_signature")):
            block_reasons.append("P15_REQUEST_TICKET_OR_SIGNATURE_MISSING")
        if str(data.get("enablement_phrase") or "") != LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE:
            block_reasons.append("P15_REQUEST_EXACT_PHRASE_MISSING")
        if not _bool(data.get("human_operator_submitted")):
            block_reasons.append("P15_REQUEST_NOT_HUMAN_SUBMITTED")
        if _bool(data.get("auto_generated_enablement_file")):
            block_reasons.append("P15_REQUEST_AUTO_GENERATED_FILE")
        if not is_canonical_utc_timestamp(str(data.get("canonical_utc_timestamp") or "")):
            block_reasons.append("P15_REQUEST_TIMESTAMP_NOT_CANONICAL_UTC")
        for ack in sorted(_REQUIRED_REQUEST_ACKS):
            if not _bool(data.get(ack)):
                block_reasons.append(f"P15_REQUEST_ACKNOWLEDGEMENT_MISSING:{ack}")
        unsafe_fields = [
            "requests_runtime_scheduler_enabled",
            "requests_runtime_loop_started",
            "requests_live_scaled_execution_enabled",
            "requests_live_order_submission_allowed",
            "requests_place_order_enabled",
            "requests_cancel_order_enabled",
            "requests_auto_promotion_allowed",
            "requests_runtime_settings_mutation",
            "requests_score_weight_mutation",
            "secret_value_accessed",
            "secret_value_logged",
            "api_key_value_logged",
            "api_secret_value_logged",
            "withdrawal_permission_requested",
            "transfer_permission_requested",
            "admin_permission_requested",
        ]
        for field_name in unsafe_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P15_REQUEST_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "runtime_enablement_request_present": bool(data),
        "runtime_enablement_request_waiting": bool(waiting_reasons),
        "runtime_enablement_request_blocked": bool(block_reasons),
        "runtime_enablement_request_waiting_reasons": sorted(set(waiting_reasons)),
        "runtime_enablement_request_block_reasons": sorted(set(block_reasons)),
        "runtime_enablement_request_id": data.get("runtime_enablement_request_id"),
        "runtime_enablement_request_sha256": _sha_from(data, "runtime_enablement_request_sha256"),
        "operator_runtime_enablement_request_valid_review_only": bool(data) and not block_reasons,
    }


def _validate_stage_policy(policy: Mapping[str, Any], p14_validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(policy or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P15_RUNTIME_STAGE_POLICY_MISSING")
    else:
        if str(data.get("stage") or "") != "limited_live_scaled":
            block_reasons.append("P15_POLICY_STAGE_INVALID")
        if not _nonempty(data.get("runtime_stage_policy_id")):
            block_reasons.append("P15_POLICY_ID_MISSING")
        p14_sha = p14_validation.get("p14_report_sha256")
        if p14_sha and data.get("source_p14_live_scaled_approval_intake_validation_sha256") != p14_sha:
            block_reasons.append("P15_POLICY_P14_HASH_MISMATCH")
        symbols = data.get("symbol_scope") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        if [str(item) for item in symbols] != ["BTCUSDT"]:
            block_reasons.append("P15_POLICY_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY")
        if _as_float(data.get("fixed_max_notional_usdt"), -1.0) <= 0 or _as_float(data.get("fixed_max_notional_usdt"), -1.0) > MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT:
            block_reasons.append("P15_POLICY_FIXED_MAX_NOTIONAL_OUT_OF_RANGE")
        if _as_float(data.get("daily_loss_cap_usdt"), -1.0) <= 0 or _as_float(data.get("daily_loss_cap_usdt"), -1.0) > MAX_DAILY_LOSS_CAP_USDT:
            block_reasons.append("P15_POLICY_DAILY_LOSS_CAP_OUT_OF_RANGE")
        if _as_int(data.get("max_daily_order_count"), -1) <= 0 or _as_int(data.get("max_daily_order_count"), -1) > MAX_DAILY_ORDER_COUNT:
            block_reasons.append("P15_POLICY_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE")
        if _as_int(data.get("max_open_position_count"), -1) <= 0 or _as_int(data.get("max_open_position_count"), -1) > MAX_OPEN_POSITION_COUNT:
            block_reasons.append("P15_POLICY_MAX_OPEN_POSITION_COUNT_OUT_OF_RANGE")
        if _as_float(data.get("max_leverage"), -1.0) <= 0 or _as_float(data.get("max_leverage"), -1.0) > MAX_LEVERAGE:
            block_reasons.append("P15_POLICY_MAX_LEVERAGE_OUT_OF_RANGE")
        if _as_float(data.get("max_slippage_bps"), -1.0) < 0 or _as_float(data.get("max_slippage_bps"), -1.0) > MAX_SLIPPAGE_BPS:
            block_reasons.append("P15_POLICY_MAX_SLIPPAGE_OUT_OF_RANGE")
        if _as_float(data.get("max_api_error_rate"), -1.0) < 0 or _as_float(data.get("max_api_error_rate"), -1.0) > MAX_API_ERROR_RATE:
            block_reasons.append("P15_POLICY_MAX_API_ERROR_RATE_OUT_OF_RANGE")
        if _as_float(data.get("max_rejection_rate"), -1.0) < 0 or _as_float(data.get("max_rejection_rate"), -1.0) > MAX_REJECTION_RATE:
            block_reasons.append("P15_POLICY_MAX_REJECTION_RATE_OUT_OF_RANGE")
        for required in sorted(_REQUIRED_POLICY_FLAGS):
            if not _bool(data.get(required)):
                block_reasons.append(f"P15_POLICY_REQUIRED_FIELD_FALSE:{required}")
        if not _bool(data.get("generated_for_review_only")):
            block_reasons.append("P15_POLICY_NOT_REVIEW_ONLY")
        unsafe_fields = [
            "runtime_scheduler_enabled",
            "runtime_loop_started",
            "live_scaled_execution_enabled",
            "live_order_submission_allowed",
            "place_order_enabled",
            "cancel_order_enabled",
            "runtime_settings_mutated",
            "score_weights_mutated",
            "secret_value_accessed",
            "withdrawal_permission_allowed",
            "transfer_permission_allowed",
            "admin_permission_allowed",
        ]
        for field_name in unsafe_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P15_POLICY_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "runtime_stage_policy_present": bool(data),
        "runtime_stage_policy_waiting": bool(waiting_reasons),
        "runtime_stage_policy_blocked": bool(block_reasons),
        "runtime_stage_policy_waiting_reasons": sorted(set(waiting_reasons)),
        "runtime_stage_policy_block_reasons": sorted(set(block_reasons)),
        "runtime_stage_policy_id": data.get("runtime_stage_policy_id"),
        "runtime_stage_policy_sha256": _sha_from(data, "runtime_stage_policy_sha256"),
        "runtime_stage_policy_valid_review_only": bool(data) and not block_reasons,
        "runtime_policy_controls": {
            "symbol_scope": data.get("symbol_scope") or [],
            "fixed_max_notional_usdt": data.get("fixed_max_notional_usdt"),
            "daily_loss_cap_usdt": data.get("daily_loss_cap_usdt"),
            "max_daily_order_count": data.get("max_daily_order_count"),
            "max_consecutive_loss_count": data.get("max_consecutive_loss_count"),
            "max_open_position_count": data.get("max_open_position_count"),
            "max_leverage": data.get("max_leverage"),
            "max_slippage_bps": data.get("max_slippage_bps"),
            "max_api_error_rate": data.get("max_api_error_rate"),
            "max_rejection_rate": data.get("max_rejection_rate"),
        },
    }


def _validate_loop_controls(controls: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(controls or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P15_RUNTIME_LOOP_CONTROLS_MISSING")
    else:
        interval = _as_int(data.get("scheduler_interval_seconds"), -1)
        if interval <= 0:
            block_reasons.append("P15_LOOP_SCHEDULER_INTERVAL_INVALID")
        for required in sorted(_REQUIRED_LOOP_FLAGS):
            if not _bool(data.get(required)):
                block_reasons.append(f"P15_LOOP_REQUIRED_FIELD_FALSE:{required}")
        unsafe_fields = [
            "runtime_scheduler_enabled",
            "runtime_loop_started",
            "live_order_endpoint_called",
            "order_endpoint_called",
            "http_request_sent",
            "signature_created",
            "signed_request_created",
            "live_scaled_execution_enabled",
            "live_order_submission_allowed",
            "place_order_enabled",
            "cancel_order_enabled",
            "auto_promotion_allowed",
            "runtime_settings_mutated",
            "score_weights_mutated",
            "secret_value_accessed",
            "secret_value_logged",
            "api_key_value_logged",
            "api_secret_value_logged",
        ]
        for field_name in unsafe_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P15_LOOP_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "runtime_loop_controls_present": bool(data),
        "runtime_loop_controls_waiting": bool(waiting_reasons),
        "runtime_loop_controls_blocked": bool(block_reasons),
        "runtime_loop_controls_waiting_reasons": sorted(set(waiting_reasons)),
        "runtime_loop_controls_block_reasons": sorted(set(block_reasons)),
        "runtime_loop_controls_id": data.get("runtime_loop_controls_id"),
        "runtime_loop_controls_sha256": _sha_from(data, "runtime_loop_controls_sha256"),
        "runtime_loop_controls_valid_review_only": bool(data) and not block_reasons,
        "scheduler_interval_seconds": data.get("scheduler_interval_seconds"),
    }


def build_limited_live_scaled_runtime_enablement_boundary_report(
    *,
    cfg: AppConfig | None = None,
    p14_report: Mapping[str, Any] | None = None,
    runtime_enablement_request: Mapping[str, Any] | None = None,
    runtime_stage_policy: Mapping[str, Any] | None = None,
    runtime_loop_controls: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if cfg is not None:
        if p14_report is None:
            p14_report = _read_latest_json(cfg, "p14_live_scaled_approval_intake_validation_report.json")
        if runtime_enablement_request is None:
            runtime_enablement_request = _read_latest_json(cfg, "p15_runtime_enablement_request.json")
        if runtime_stage_policy is None:
            runtime_stage_policy = _read_latest_json(cfg, "p15_runtime_stage_policy.json")
        if runtime_loop_controls is None:
            runtime_loop_controls = _read_latest_json(cfg, "p15_runtime_loop_controls.json")

    p14_validation = _validate_p14_source(p14_report or {})
    request_validation = _validate_enablement_request(runtime_enablement_request or {}, p14_validation)
    policy_validation = _validate_stage_policy(runtime_stage_policy or {}, p14_validation)
    loop_validation = _validate_loop_controls(runtime_loop_controls or {})

    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    block_reasons.extend(p14_validation["p14_source_block_reasons"])
    block_reasons.extend(request_validation["runtime_enablement_request_block_reasons"])
    block_reasons.extend(policy_validation["runtime_stage_policy_block_reasons"])
    block_reasons.extend(loop_validation["runtime_loop_controls_block_reasons"])
    waiting_reasons.extend(p14_validation["p14_source_waiting_reasons"])
    waiting_reasons.extend(request_validation["runtime_enablement_request_waiting_reasons"])
    waiting_reasons.extend(policy_validation["runtime_stage_policy_waiting_reasons"])
    waiting_reasons.extend(loop_validation["runtime_loop_controls_waiting_reasons"])

    blocked = bool(block_reasons)
    waiting = bool(waiting_reasons) and not blocked
    boundary_valid = not blocked and not waiting
    status = (
        STATUS_BLOCKED_FAIL_CLOSED
        if blocked
        else (STATUS_WAITING_REVIEW_ONLY if waiting else STATUS_VALID_REVIEW_ONLY_NO_EXECUTION)
    )
    report_id_source = {
        "status": status,
        "p14": p14_validation.get("p14_report_sha256"),
        "request": request_validation.get("runtime_enablement_request_sha256"),
        "policy": policy_validation.get("runtime_stage_policy_sha256"),
        "loop": loop_validation.get("runtime_loop_controls_sha256"),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
    }
    disabled = _disabled_payload()
    report = {
        "version": P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_VERSION,
        "p15_limited_live_scaled_runtime_enablement_boundary_id": stable_id(
            "p15_limited_live_scaled_runtime_enablement_boundary", report_id_source, 24
        ),
        "status": status,
        "review_only": True,
        "blocked": blocked,
        "waiting": waiting,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "p14_source_validation": p14_validation,
        "runtime_enablement_request_validation": request_validation,
        "runtime_stage_policy_validation": policy_validation,
        "runtime_loop_controls_validation": loop_validation,
        "source_p14_live_scaled_approval_intake_validation_sha256": p14_validation.get("p14_report_sha256"),
        "runtime_enablement_request_sha256": request_validation.get("runtime_enablement_request_sha256"),
        "runtime_stage_policy_sha256": policy_validation.get("runtime_stage_policy_sha256"),
        "runtime_loop_controls_sha256": loop_validation.get("runtime_loop_controls_sha256"),
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": boundary_valid,
        "runtime_stage_policy_valid_review_only": boundary_valid and policy_validation["runtime_stage_policy_valid_review_only"],
        "runtime_loop_controls_valid_review_only": boundary_valid and loop_validation["runtime_loop_controls_valid_review_only"],
        "operator_runtime_enablement_request_valid_review_only": boundary_valid
        and request_validation["operator_runtime_enablement_request_valid_review_only"],
        "limited_live_scaled_runtime_boundary_ready_review_only": boundary_valid,
        "separate_operator_runtime_process_required": True,
        "scheduler_loop_design_validated_review_only": boundary_valid,
        "current_stage_policy_required": True,
        "fresh_data_signal_risk_refresh_required": True,
        "hot_path_preorder_risk_gate_required": True,
        "hard_caps_required": True,
        "kill_switches_required": True,
        "idempotency_and_duplicate_submit_lock_required": True,
        "post_submit_relock_required": True,
        "status_polling_required": True,
        "reconciliation_required": True,
        "outcome_feedback_required": True,
        "daily_report_required": True,
        "incident_report_required": True,
        "all_orders_must_reconcile": True,
        "canonical_id_chain_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "limited_live_scaled_auto_trading_allowed_by_this_module": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_runtime_enablement_performed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "actual_live_order_submitted": False,
        "actual_live_order_submitted_by_this_module": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
        "review_notes": [
            "p15_validates_limited_live_scaled_runtime_boundary_only",
            "p15_does_not_start_scheduler_or_submit_orders",
            "separate_operator_runtime_process_and_fresh_checks_required_before_any_execution",
        ],
        **disabled,
    }
    # Preserve P15 review booleans after merging disabled defaults.
    report["p15_limited_live_scaled_runtime_boundary_valid_review_only"] = boundary_valid
    report["runtime_stage_policy_valid_review_only"] = boundary_valid and policy_validation["runtime_stage_policy_valid_review_only"]
    report["runtime_loop_controls_valid_review_only"] = boundary_valid and loop_validation["runtime_loop_controls_valid_review_only"]
    report["operator_runtime_enablement_request_valid_review_only"] = boundary_valid and request_validation[
        "operator_runtime_enablement_request_valid_review_only"
    ]
    report["limited_live_scaled_runtime_boundary_ready_review_only"] = boundary_valid
    report["limited_live_scaled_auto_trading_allowed"] = False
    report["live_scaled_runtime_enablement_allowed"] = False
    report["runtime_scheduler_enabled"] = False
    report["runtime_loop_started"] = False
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    report["p15_limited_live_scaled_runtime_enablement_boundary_sha256"] = sha256_json(report)
    return report


def build_p15_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    valid_p14 = {
        "status": "P14_LIVE_SCALED_APPROVAL_INTAKE_VALID_REVIEW_ONLY_NO_EXECUTION",
        "p14_live_scaled_approval_intake_validation_sha256": "f" * 64,
        "live_scaled_approval_valid_review_only": True,
        "live_scaled_approval_packet_valid": True,
        "live_scaled_approval_intake_valid": True,
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    valid_request = build_valid_runtime_enablement_request(valid_p14)
    valid_policy = build_review_only_runtime_stage_policy(valid_p14)
    valid_loop = build_review_only_runtime_loop_controls()
    fixtures: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]] = {
        "p14_not_valid": ({**valid_p14, "live_scaled_approval_valid_review_only": False}, valid_request, valid_policy, valid_loop),
        "request_p14_hash_mismatch": (valid_p14, {**valid_request, "source_p14_live_scaled_approval_intake_validation_sha256": "x" * 64}, valid_policy, valid_loop),
        "missing_runtime_enablement_phrase": (valid_p14, {**valid_request, "enablement_phrase": "APPROVED"}, valid_policy, valid_loop),
        "request_enable_scheduler": (valid_p14, {**valid_request, "requests_runtime_scheduler_enabled": True}, valid_policy, valid_loop),
        "policy_symbol_scope_not_btc_only": (valid_p14, valid_request, {**valid_policy, "symbol_scope": ["BTCUSDT", "ETHUSDT"]}, valid_loop),
        "policy_notional_cap_too_high": (valid_p14, valid_request, {**valid_policy, "fixed_max_notional_usdt": 999.0}, valid_loop),
        "policy_daily_loss_cap_too_high": (valid_p14, valid_request, {**valid_policy, "daily_loss_cap_usdt": 999.0}, valid_loop),
        "policy_max_daily_order_count_too_high": (valid_p14, valid_request, {**valid_policy, "max_daily_order_count": 99}, valid_loop),
        "policy_max_leverage_too_high": (valid_p14, valid_request, {**valid_policy, "max_leverage": 25.0}, valid_loop),
        "policy_missing_risk_gate_requirement": (valid_p14, valid_request, {**valid_policy, "requires_hot_path_preorder_risk_gate": False}, valid_loop),
        "loop_missing_fresh_data": (valid_p14, valid_request, valid_policy, {**valid_loop, "fresh_market_data_required": False}),
        "loop_missing_idempotency": (valid_p14, valid_request, valid_policy, {**valid_loop, "idempotency_key_required": False}),
        "loop_missing_reconciliation": (valid_p14, valid_request, valid_policy, {**valid_loop, "reconciliation_required": False}),
        "loop_missing_daily_report": (valid_p14, valid_request, valid_policy, {**valid_loop, "daily_report_required": False}),
        "loop_missing_incident_report": (valid_p14, valid_request, valid_policy, {**valid_loop, "incident_report_required": False}),
        "loop_scheduler_enabled": (valid_p14, valid_request, valid_policy, {**valid_loop, "runtime_scheduler_enabled": True}),
        "live_order_allowed": (valid_p14, valid_request, valid_policy, {**valid_loop, "live_order_submission_allowed": True}),
        "place_order_enabled": (valid_p14, valid_request, valid_policy, {**valid_loop, "place_order_enabled": True}),
        "secret_leak": (valid_p14, valid_request, valid_policy, {**valid_loop, "secret_value_logged": True}),
        "runtime_mutation": (valid_p14, valid_request, valid_policy, {**valid_loop, "runtime_settings_mutated": True}),
    }
    results: dict[str, Any] = {}
    for name, (p14, request, policy, loop) in fixtures.items():
        report = build_limited_live_scaled_runtime_enablement_boundary_report(
            cfg=cfg,
            p14_report=p14,
            runtime_enablement_request=request,
            runtime_stage_policy=policy,
            runtime_loop_controls=loop,
        )
        results[name] = {
            "status": report["status"],
            "blocked_fail_closed": report["status"] == STATUS_BLOCKED_FAIL_CLOSED or bool(report["block_reasons"]) or bool(report["waiting_reasons"]),
            "waiting": report["waiting"],
            "p15_limited_live_scaled_runtime_boundary_valid_review_only": report[
                "p15_limited_live_scaled_runtime_boundary_valid_review_only"
            ],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "version": P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_VERSION,
        "fixture_results": results,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    payload["p15_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_limited_live_scaled_runtime_enablement_boundary(
    *,
    cfg: AppConfig | None = None,
    p14_report: Mapping[str, Any] | None = None,
    runtime_enablement_request: Mapping[str, Any] | None = None,
    runtime_stage_policy: Mapping[str, Any] | None = None,
    runtime_loop_controls: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    if p14_report is None:
        p14_report = _read_latest_json(cfg, "p14_live_scaled_approval_intake_validation_report.json")
    if runtime_enablement_request is None:
        runtime_enablement_request = _read_latest_json(cfg, "p15_runtime_enablement_request.json")
    if runtime_stage_policy is None:
        runtime_stage_policy = _read_latest_json(cfg, "p15_runtime_stage_policy.json")
    if runtime_loop_controls is None:
        runtime_loop_controls = _read_latest_json(cfg, "p15_runtime_loop_controls.json")

    p14_validation = _validate_p14_source(p14_report or {})
    if p14_validation["p14_live_scaled_approval_valid_review_only"] and not p14_validation["p14_source_blocked"]:
        if not runtime_stage_policy:
            runtime_stage_policy = build_review_only_runtime_stage_policy(p14_report or {})
            atomic_write_json(latest / "p15_runtime_stage_policy.json", runtime_stage_policy)
        if not runtime_loop_controls:
            runtime_loop_controls = build_review_only_runtime_loop_controls()
            atomic_write_json(latest / "p15_runtime_loop_controls.json", runtime_loop_controls)

    report = build_limited_live_scaled_runtime_enablement_boundary_report(
        cfg=cfg,
        p14_report=p14_report,
        runtime_enablement_request=runtime_enablement_request,
        runtime_stage_policy=runtime_stage_policy,
        runtime_loop_controls=runtime_loop_controls,
    )
    negative = build_p15_negative_fixture_results(cfg=cfg)
    atomic_write_json(latest / "p15_limited_live_scaled_runtime_enablement_boundary_report.json", report)
    summary = {
        "version": P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": report[
            "p15_limited_live_scaled_runtime_boundary_valid_review_only"
        ],
        "runtime_stage_policy_valid_review_only": report["runtime_stage_policy_valid_review_only"],
        "runtime_loop_controls_valid_review_only": report["runtime_loop_controls_valid_review_only"],
        "operator_runtime_enablement_request_valid_review_only": report["operator_runtime_enablement_request_valid_review_only"],
        "limited_live_scaled_runtime_boundary_ready_review_only": report["limited_live_scaled_runtime_boundary_ready_review_only"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "p15_limited_live_scaled_runtime_enablement_boundary_sha256": report[
            "p15_limited_live_scaled_runtime_enablement_boundary_sha256"
        ],
    }
    atomic_write_json(latest / "p15_limited_live_scaled_runtime_enablement_boundary_summary.json", summary)
    atomic_write_json(latest / "p15_limited_live_scaled_runtime_enablement_boundary_negative_fixture_results.json", negative)
    archive_dir = _storage_dir(cfg, "storage/p15_limited_live_scaled_runtime_enablement_boundary")
    atomic_write_json(archive_dir / "p15_limited_live_scaled_runtime_enablement_boundary_report.json", report)
    registry_record = {
        "version": P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "p15_limited_live_scaled_runtime_boundary_valid_review_only": report[
            "p15_limited_live_scaled_runtime_boundary_valid_review_only"
        ],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "report_sha256": report["p15_limited_live_scaled_runtime_enablement_boundary_sha256"],
    }
    registry_record = append_registry_record(
        registry_path(cfg, P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_REGISTRY_NAME),
        registry_record,
        registry_name=P15_LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_REGISTRY_NAME,
        id_field="p15_limited_live_scaled_runtime_enablement_boundary_record_id",
        hash_field="p15_limited_live_scaled_runtime_enablement_boundary_registry_record_sha256",
        id_prefix="p15_limited_live_scaled_runtime_enablement_boundary",
    )
    atomic_write_json(latest / "p15_limited_live_scaled_runtime_enablement_boundary_registry_record.json", registry_record)
    return report


__all__ = [
    "LIMITED_LIVE_SCALED_RUNTIME_ENABLEMENT_PHRASE",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "STATUS_VALID_REVIEW_ONLY_NO_EXECUTION",
    "STATUS_WAITING_REVIEW_ONLY",
    "LimitedLiveScaledRuntimeEnablementRequest",
    "LimitedLiveScaledRuntimeLoopControls",
    "LimitedLiveScaledRuntimeStagePolicy",
    "build_limited_live_scaled_runtime_enablement_boundary_report",
    "build_p15_negative_fixture_results",
    "build_review_only_runtime_loop_controls",
    "build_review_only_runtime_stage_policy",
    "build_valid_runtime_enablement_request",
    "persist_limited_live_scaled_runtime_enablement_boundary",
]
