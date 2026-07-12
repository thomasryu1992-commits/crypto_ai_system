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
    MAX_SLIPPAGE_BPS,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

P14_LIVE_SCALED_APPROVAL_INTAKE_VERSION = "p14_live_scaled_approval_intake_validation_v1"
P14_LIVE_SCALED_APPROVAL_INTAKE_REGISTRY_NAME = "p14_live_scaled_approval_intake_validation_registry"

STATUS_WAITING_REVIEW_ONLY = "P14_LIVE_SCALED_APPROVAL_INTAKE_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY_NO_EXECUTION = "P14_LIVE_SCALED_APPROVAL_INTAKE_VALID_REVIEW_ONLY_NO_EXECUTION"
STATUS_BLOCKED_FAIL_CLOSED = "P14_LIVE_SCALED_APPROVAL_INTAKE_BLOCKED_FAIL_CLOSED"

LIVE_SCALED_APPROVAL_PHRASE = "I APPROVE LIMITED LIVE SCALED AUTO TRADING REVIEW GATE ONLY - NO EXECUTION"

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
    "actual_live_order_submitted": False,
    "actual_live_order_submitted_by_this_module": False,
    "live_order_endpoint_called": False,
    "order_endpoint_called": False,
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
            "p14_live_scaled_approval_intake_validation_started": False,
            "live_scaled_approval_packet_valid": False,
            "live_scaled_approval_intake_valid": False,
            "live_scaled_approval_valid_review_only": False,
            "live_scaled_runtime_enablement_allowed": False,
            "limited_live_scaled_auto_trading_allowed": False,
            "separate_runtime_enablement_step_required": True,
        }
    )
    return payload


@dataclass(frozen=True)
class LiveScaledApprovalPacket:
    stage: str = "limited_live_scaled"
    approval_packet_id: str = "p14_live_scaled_approval_packet_review_only"
    source_p13_live_scaled_readiness_review_sha256: str = field(default_factory=lambda: "d" * 64)
    p13_status_required: str = "P13_LIVE_SCALED_READINESS_REVIEW_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY"
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
    requires_manual_operator_intake: bool = True
    requires_separate_runtime_enablement_step: bool = True
    requires_kill_switch_acknowledgement: bool = True
    requires_rollback_acknowledgement: bool = True
    requires_daily_report_acknowledgement: bool = True
    requires_incident_report_acknowledgement: bool = True
    requires_no_secret_value_access_acknowledgement: bool = True
    requires_no_runtime_mutation_acknowledgement: bool = True
    generated_for_review_only: bool = True
    auto_apply_allowed: bool = False
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
        payload["live_scaled_approval_packet_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class LiveScaledApprovalIntake:
    approval_intake_id: str = "p14_live_scaled_approval_intake_review_only"
    approval_packet_id: str = "p14_live_scaled_approval_packet_review_only"
    approval_packet_sha256: str = field(default_factory=lambda: "e" * 64)
    source_p13_live_scaled_readiness_review_sha256: str = field(default_factory=lambda: "d" * 64)
    requested_stage: str = "limited_live_scaled"
    operator_id: str = "operator_thomas_manual_review"
    ticket_or_signature: str = field(default_factory=lambda: f"LIVE-SCALED-REVIEW-{stable_id('ticket', {'phase': 14}, 8)}")
    approval_phrase: str = LIVE_SCALED_APPROVAL_PHRASE
    human_operator_submitted: bool = True
    auto_generated_approval_file: bool = False
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
    acknowledged_rollback_and_full_shutdown: bool = True
    acknowledged_monitoring_alerting: bool = True
    acknowledged_daily_report_required: bool = True
    acknowledged_incident_report_required: bool = True
    acknowledged_all_orders_must_reconcile: bool = True
    acknowledged_no_secret_values_in_logs: bool = True
    acknowledged_no_runtime_mutation_by_approval: bool = True
    acknowledged_separate_runtime_enablement_required: bool = True
    requests_live_scaled_execution_enabled: bool = False
    requests_live_order_submission_allowed: bool = False
    requests_place_order_enabled: bool = False
    requests_cancel_order_enabled: bool = False
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
        payload["live_scaled_approval_intake_sha256"] = sha256_json(payload)
        return payload


def build_review_only_live_scaled_approval_packet(p13_report: Mapping[str, Any]) -> dict[str, Any]:
    p13_sha = _sha_from(p13_report, "p13_live_scaled_readiness_review_sha256", "live_scaled_readiness_review_sha256") or "d" * 64
    packet = LiveScaledApprovalPacket(source_p13_live_scaled_readiness_review_sha256=p13_sha)
    return packet.to_dict()


def build_valid_live_scaled_approval_intake(packet: Mapping[str, Any]) -> dict[str, Any]:
    packet_sha = _sha_from(packet, "live_scaled_approval_packet_sha256") or sha256_json(dict(packet or {}))
    intake = LiveScaledApprovalIntake(
        approval_packet_id=str(packet.get("approval_packet_id") or "p14_live_scaled_approval_packet_review_only"),
        approval_packet_sha256=packet_sha,
        source_p13_live_scaled_readiness_review_sha256=str(packet.get("source_p13_live_scaled_readiness_review_sha256") or "d" * 64),
    )
    return intake.to_dict()


def _validate_p13_source(p13_report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(p13_report or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P14_SOURCE_P13_REPORT_MISSING")
    elif not _bool(data.get("ready_for_separate_live_scaled_approval_review_only")):
        waiting_reasons.append("P14_SOURCE_P13_NOT_READY_FOR_SEPARATE_APPROVAL")
    else:
        if not _bool(data.get("live_scaled_approval_packet_may_be_drafted")):
            block_reasons.append("P14_SOURCE_P13_APPROVAL_PACKET_DRAFT_NOT_ALLOWED")
        if _bool(data.get("separate_live_scaled_approval_present")):
            block_reasons.append("P14_SOURCE_P13_ALREADY_HAS_APPROVAL_PRESENT")
        if _bool(data.get("live_scaled_execution_enabled")):
            block_reasons.append("P14_SOURCE_P13_LIVE_SCALED_ALREADY_ENABLED")
    unsafe_fields = [
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
            block_reasons.append(f"P14_SOURCE_P13_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "p13_source_present": bool(data),
        "p13_source_waiting": bool(waiting_reasons),
        "p13_source_blocked": bool(block_reasons),
        "p13_source_waiting_reasons": sorted(set(waiting_reasons)),
        "p13_source_block_reasons": sorted(set(block_reasons)),
        "p13_ready_for_separate_live_scaled_approval_review_only": _bool(data.get("ready_for_separate_live_scaled_approval_review_only")),
        "p13_live_scaled_approval_packet_may_be_drafted": _bool(data.get("live_scaled_approval_packet_may_be_drafted")),
        "p13_report_sha256": _sha_from(data, "p13_live_scaled_readiness_review_sha256", "live_scaled_readiness_review_sha256"),
    }


def _validate_packet(packet: Mapping[str, Any], p13_validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(packet or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P14_APPROVAL_PACKET_MISSING")
    else:
        if str(data.get("stage") or "") != "limited_live_scaled":
            block_reasons.append("P14_PACKET_STAGE_INVALID")
        if not _nonempty(data.get("approval_packet_id")):
            block_reasons.append("P14_PACKET_ID_MISSING")
        p13_sha = p13_validation.get("p13_report_sha256")
        if p13_sha and data.get("source_p13_live_scaled_readiness_review_sha256") != p13_sha:
            block_reasons.append("P14_PACKET_P13_HASH_MISMATCH")
        symbols = data.get("symbol_scope") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        if [str(item) for item in symbols] != ["BTCUSDT"]:
            block_reasons.append("P14_PACKET_SYMBOL_SCOPE_NOT_BTCUSDT_ONLY")
        if _as_float(data.get("fixed_max_notional_usdt"), -1.0) <= 0 or _as_float(data.get("fixed_max_notional_usdt"), -1.0) > MAX_LIMITED_LIVE_SCALED_NOTIONAL_USDT:
            block_reasons.append("P14_PACKET_FIXED_MAX_NOTIONAL_OUT_OF_RANGE")
        if _as_float(data.get("daily_loss_cap_usdt"), -1.0) <= 0 or _as_float(data.get("daily_loss_cap_usdt"), -1.0) > MAX_DAILY_LOSS_CAP_USDT:
            block_reasons.append("P14_PACKET_DAILY_LOSS_CAP_OUT_OF_RANGE")
        if _as_int(data.get("max_daily_order_count"), -1) <= 0 or _as_int(data.get("max_daily_order_count"), -1) > MAX_DAILY_ORDER_COUNT:
            block_reasons.append("P14_PACKET_MAX_DAILY_ORDER_COUNT_OUT_OF_RANGE")
        if _as_int(data.get("max_open_position_count"), -1) <= 0 or _as_int(data.get("max_open_position_count"), -1) > MAX_OPEN_POSITION_COUNT:
            block_reasons.append("P14_PACKET_MAX_OPEN_POSITION_COUNT_OUT_OF_RANGE")
        if _as_float(data.get("max_leverage"), -1.0) <= 0 or _as_float(data.get("max_leverage"), -1.0) > MAX_LEVERAGE:
            block_reasons.append("P14_PACKET_MAX_LEVERAGE_OUT_OF_RANGE")
        if _as_float(data.get("max_slippage_bps"), -1.0) < 0 or _as_float(data.get("max_slippage_bps"), -1.0) > MAX_SLIPPAGE_BPS:
            block_reasons.append("P14_PACKET_MAX_SLIPPAGE_OUT_OF_RANGE")
        if _as_float(data.get("max_api_error_rate"), -1.0) < 0 or _as_float(data.get("max_api_error_rate"), -1.0) > MAX_API_ERROR_RATE:
            block_reasons.append("P14_PACKET_MAX_API_ERROR_RATE_OUT_OF_RANGE")
        for required in [
            "requires_manual_operator_intake",
            "requires_separate_runtime_enablement_step",
            "requires_kill_switch_acknowledgement",
            "requires_rollback_acknowledgement",
            "requires_daily_report_acknowledgement",
            "requires_incident_report_acknowledgement",
            "requires_no_secret_value_access_acknowledgement",
            "requires_no_runtime_mutation_acknowledgement",
            "generated_for_review_only",
        ]:
            if not _bool(data.get(required)):
                block_reasons.append(f"P14_PACKET_REQUIRED_FIELD_FALSE:{required}")
        unsafe_false_fields = [
            "auto_apply_allowed",
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
        for field_name in unsafe_false_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P14_PACKET_UNSAFE_FLAG_TRUE:{field_name}")
    return {
        "approval_packet_present": bool(data),
        "approval_packet_waiting": bool(waiting_reasons),
        "approval_packet_blocked": bool(block_reasons),
        "approval_packet_waiting_reasons": sorted(set(waiting_reasons)),
        "approval_packet_block_reasons": sorted(set(block_reasons)),
        "approval_packet_id": data.get("approval_packet_id"),
        "approval_packet_sha256": _sha_from(data, "live_scaled_approval_packet_sha256"),
        "approval_packet_valid": bool(data) and not block_reasons,
    }


def _validate_intake(intake: Mapping[str, Any], packet_validation: Mapping[str, Any], p13_validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(intake or {})
    block_reasons: list[str] = []
    waiting_reasons: list[str] = []
    if not data:
        waiting_reasons.append("P14_APPROVAL_INTAKE_MISSING")
    else:
        if str(data.get("requested_stage") or "") != "limited_live_scaled":
            block_reasons.append("P14_INTAKE_STAGE_INVALID")
        if not _nonempty(data.get("approval_intake_id")):
            block_reasons.append("P14_INTAKE_ID_MISSING")
        if not _nonempty(data.get("operator_id")):
            block_reasons.append("P14_INTAKE_OPERATOR_ID_MISSING")
        if not _nonempty(data.get("ticket_or_signature")):
            block_reasons.append("P14_INTAKE_TICKET_OR_SIGNATURE_MISSING")
        if data.get("approval_phrase") != LIVE_SCALED_APPROVAL_PHRASE:
            block_reasons.append("P14_INTAKE_EXACT_APPROVAL_PHRASE_MISSING")
        if data.get("human_operator_submitted") is not True:
            block_reasons.append("P14_INTAKE_NOT_HUMAN_OPERATOR_SUBMITTED")
        if _bool(data.get("auto_generated_approval_file")):
            block_reasons.append("P14_INTAKE_AUTO_GENERATED_APPROVAL_FILE_BLOCKED")
        if not is_canonical_utc_timestamp(data.get("canonical_utc_timestamp")):
            block_reasons.append("P14_INTAKE_CANONICAL_TIMESTAMP_INVALID")
        if data.get("approval_packet_id") != packet_validation.get("approval_packet_id"):
            block_reasons.append("P14_INTAKE_APPROVAL_PACKET_ID_MISMATCH")
        if packet_validation.get("approval_packet_sha256") and data.get("approval_packet_sha256") != packet_validation.get("approval_packet_sha256"):
            block_reasons.append("P14_INTAKE_APPROVAL_PACKET_HASH_MISMATCH")
        if p13_validation.get("p13_report_sha256") and data.get("source_p13_live_scaled_readiness_review_sha256") != p13_validation.get("p13_report_sha256"):
            block_reasons.append("P14_INTAKE_P13_HASH_MISMATCH")
        required_ack = [
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
            "acknowledged_rollback_and_full_shutdown",
            "acknowledged_monitoring_alerting",
            "acknowledged_daily_report_required",
            "acknowledged_incident_report_required",
            "acknowledged_all_orders_must_reconcile",
            "acknowledged_no_secret_values_in_logs",
            "acknowledged_no_runtime_mutation_by_approval",
            "acknowledged_separate_runtime_enablement_required",
        ]
        for field_name in required_ack:
            if data.get(field_name) is not True:
                block_reasons.append(f"P14_INTAKE_REQUIRED_ACK_MISSING:{field_name}")
        unsafe_request_fields = [
            "requests_live_scaled_execution_enabled",
            "requests_live_order_submission_allowed",
            "requests_place_order_enabled",
            "requests_cancel_order_enabled",
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
        for field_name in unsafe_request_fields:
            if _bool(data.get(field_name)):
                block_reasons.append(f"P14_INTAKE_UNSAFE_REQUEST_TRUE:{field_name}")
    return {
        "approval_intake_present": bool(data),
        "approval_intake_waiting": bool(waiting_reasons),
        "approval_intake_blocked": bool(block_reasons),
        "approval_intake_waiting_reasons": sorted(set(waiting_reasons)),
        "approval_intake_block_reasons": sorted(set(block_reasons)),
        "approval_intake_id": data.get("approval_intake_id"),
        "approval_intake_sha256": _sha_from(data, "live_scaled_approval_intake_sha256"),
        "approval_intake_valid": bool(data) and not block_reasons,
    }


def build_live_scaled_approval_intake_validation_report(
    *,
    cfg: AppConfig | None = None,
    p13_report: Mapping[str, Any] | None = None,
    approval_packet: Mapping[str, Any] | None = None,
    approval_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if cfg is not None:
        if p13_report is None:
            p13_report = _read_latest_json(cfg, "p13_live_scaled_readiness_review_report.json")
        if approval_packet is None:
            approval_packet = _read_latest_json(cfg, "p14_live_scaled_approval_packet.json")
        if approval_intake is None:
            approval_intake = _read_latest_json(cfg, "p14_live_scaled_approval_intake.json")
    p13 = dict(p13_report or {})
    packet = dict(approval_packet or {})
    intake = dict(approval_intake or {})

    p13_validation = _validate_p13_source(p13)
    packet_validation = _validate_packet(packet, p13_validation)
    intake_validation = _validate_intake(intake, packet_validation, p13_validation)

    waiting_reasons = []
    block_reasons = []
    waiting_reasons.extend(p13_validation["p13_source_waiting_reasons"])
    block_reasons.extend(p13_validation["p13_source_block_reasons"])
    waiting_reasons.extend(packet_validation["approval_packet_waiting_reasons"])
    block_reasons.extend(packet_validation["approval_packet_block_reasons"])
    waiting_reasons.extend(intake_validation["approval_intake_waiting_reasons"])
    block_reasons.extend(intake_validation["approval_intake_block_reasons"])

    # When P13 is not ready yet, a packet/intake absence is informational waiting, not a blocker.
    if p13_validation["p13_source_waiting"]:
        block_reasons = [reason for reason in block_reasons if not reason.startswith("P14_APPROVAL_")]

    status = STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    if block_reasons:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY

    approval_valid = status == STATUS_VALID_REVIEW_ONLY_NO_EXECUTION
    disabled = _disabled_payload()
    report: dict[str, Any] = {
        "version": P14_LIVE_SCALED_APPROVAL_INTAKE_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "waiting": status == STATUS_WAITING_REVIEW_ONLY,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "p13_validation": p13_validation,
        "approval_packet_validation": packet_validation,
        "approval_intake_validation": intake_validation,
        "live_scaled_approval_valid_review_only": approval_valid,
        "live_scaled_approval_packet_valid": approval_valid and packet_validation["approval_packet_valid"],
        "live_scaled_approval_intake_valid": approval_valid and intake_validation["approval_intake_valid"],
        "live_scaled_approval_packet_id": packet_validation.get("approval_packet_id"),
        "live_scaled_approval_intake_id": intake_validation.get("approval_intake_id"),
        "source_p13_live_scaled_readiness_review_sha256": p13_validation.get("p13_report_sha256"),
        "approval_packet_sha256": packet_validation.get("approval_packet_sha256"),
        "approval_intake_sha256": intake_validation.get("approval_intake_sha256"),
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_scaled_promotion_allowed": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "secret_file_accessed": False,
        "secret_file_created": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
        "review_notes": [
            "separate_live_scaled_approval_validates_review_chain_only",
            "approval_does_not_enable_runtime_or_order_submission",
            "separate_runtime_enablement_gate_required_after_this_stage",
        ],
        **disabled,
    }
    # Preserve the report-level approval result after merging disabled defaults.
    report["live_scaled_approval_valid_review_only"] = approval_valid
    report["live_scaled_approval_packet_valid"] = approval_valid and packet_validation["approval_packet_valid"]
    report["live_scaled_approval_intake_valid"] = approval_valid and intake_validation["approval_intake_valid"]
    report["limited_live_scaled_auto_trading_allowed"] = False
    report["live_scaled_runtime_enablement_allowed"] = False
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    report["p14_live_scaled_approval_intake_validation_sha256"] = sha256_json(report)
    return report


def build_p14_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    valid_p13 = {
        "status": "P13_LIVE_SCALED_READINESS_REVIEW_READY_FOR_SEPARATE_APPROVAL_REVIEW_ONLY",
        "p13_live_scaled_readiness_review_sha256": "d" * 64,
        "ready_for_separate_live_scaled_approval_review_only": True,
        "live_scaled_approval_packet_may_be_drafted": True,
        "separate_live_scaled_approval_required": True,
        "separate_live_scaled_approval_present": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    valid_packet = build_review_only_live_scaled_approval_packet(valid_p13)
    valid_intake = build_valid_live_scaled_approval_intake(valid_packet)
    fixtures: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {
        "p13_not_ready": ({**valid_p13, "ready_for_separate_live_scaled_approval_review_only": False}, valid_packet, valid_intake),
        "packet_p13_hash_mismatch": (valid_p13, {**valid_packet, "source_p13_live_scaled_readiness_review_sha256": "x" * 64}, valid_intake),
        "packet_cap_too_high": (valid_p13, {**valid_packet, "fixed_max_notional_usdt": 999.0}, valid_intake),
        "packet_symbol_scope_not_btc_only": (valid_p13, {**valid_packet, "symbol_scope": ["BTCUSDT", "ETHUSDT"]}, valid_intake),
        "packet_auto_apply_enabled": (valid_p13, {**valid_packet, "auto_apply_allowed": True}, valid_intake),
        "missing_operator_identity": (valid_p13, valid_packet, {**valid_intake, "operator_id": ""}),
        "missing_ticket_signature": (valid_p13, valid_packet, {**valid_intake, "ticket_or_signature": ""}),
        "missing_exact_phrase": (valid_p13, valid_packet, {**valid_intake, "approval_phrase": "APPROVED"}),
        "auto_generated_intake": (valid_p13, valid_packet, {**valid_intake, "auto_generated_approval_file": True}),
        "missing_caps_acknowledgement": (valid_p13, valid_packet, {**valid_intake, "acknowledged_fixed_max_notional_cap": False}),
        "missing_kill_switch_acknowledgement": (valid_p13, valid_packet, {**valid_intake, "acknowledged_kill_switches": False}),
        "requests_live_scaled_enablement": (valid_p13, valid_packet, {**valid_intake, "requests_live_scaled_execution_enabled": True}),
        "requests_order_submission": (valid_p13, valid_packet, {**valid_intake, "requests_live_order_submission_allowed": True}),
        "secret_leak": (valid_p13, valid_packet, {**valid_intake, "secret_value_logged": True}),
        "withdrawal_permission_requested": (valid_p13, valid_packet, {**valid_intake, "withdrawal_permission_requested": True}),
        "runtime_mutation_requested": (valid_p13, valid_packet, {**valid_intake, "requests_runtime_settings_mutation": True}),
    }
    results: dict[str, Any] = {}
    for name, (p13, packet, intake) in fixtures.items():
        report = build_live_scaled_approval_intake_validation_report(
            cfg=cfg,
            p13_report=p13,
            approval_packet=packet,
            approval_intake=intake,
        )
        results[name] = {
            "status": report["status"],
            "blocked_fail_closed": report["status"] == STATUS_BLOCKED_FAIL_CLOSED or bool(report["block_reasons"]) or bool(report["waiting_reasons"]),
            "waiting": report["waiting"],
            "live_scaled_approval_valid_review_only": report["live_scaled_approval_valid_review_only"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    payload = {
        "version": P14_LIVE_SCALED_APPROVAL_INTAKE_VERSION,
        "fixture_results": results,
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    payload["p14_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_live_scaled_approval_intake_validation(
    *,
    cfg: AppConfig | None = None,
    p13_report: Mapping[str, Any] | None = None,
    approval_packet: Mapping[str, Any] | None = None,
    approval_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    if p13_report is None:
        p13_report = _read_latest_json(cfg, "p13_live_scaled_readiness_review_report.json")
    if approval_packet is None:
        approval_packet = _read_latest_json(cfg, "p14_live_scaled_approval_packet.json")
    if approval_intake is None:
        approval_intake = _read_latest_json(cfg, "p14_live_scaled_approval_intake.json")

    # If P13 is ready and no packet exists, persist a review-only packet draft only.
    p13_validation = _validate_p13_source(p13_report or {})
    if not approval_packet and p13_validation["p13_ready_for_separate_live_scaled_approval_review_only"] and not p13_validation["p13_source_blocked"]:
        approval_packet = build_review_only_live_scaled_approval_packet(p13_report or {})
        atomic_write_json(latest / "p14_live_scaled_approval_packet.json", approval_packet)

    report = build_live_scaled_approval_intake_validation_report(
        cfg=cfg,
        p13_report=p13_report,
        approval_packet=approval_packet,
        approval_intake=approval_intake,
    )
    negative = build_p14_negative_fixture_results(cfg=cfg)
    atomic_write_json(latest / "p14_live_scaled_approval_intake_validation_report.json", report)
    summary = {
        "version": P14_LIVE_SCALED_APPROVAL_INTAKE_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "live_scaled_approval_valid_review_only": report["live_scaled_approval_valid_review_only"],
        "live_scaled_approval_packet_valid": report["live_scaled_approval_packet_valid"],
        "live_scaled_approval_intake_valid": report["live_scaled_approval_intake_valid"],
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "block_reasons": report["block_reasons"],
        "waiting_reasons": report["waiting_reasons"],
        "p14_live_scaled_approval_intake_validation_sha256": report["p14_live_scaled_approval_intake_validation_sha256"],
    }
    atomic_write_json(latest / "p14_live_scaled_approval_intake_validation_summary.json", summary)
    atomic_write_json(latest / "p14_live_scaled_approval_intake_validation_negative_fixture_results.json", negative)
    archive_dir = _storage_dir(cfg, "storage/p14_live_scaled_approval_intake_validation")
    atomic_write_json(archive_dir / "p14_live_scaled_approval_intake_validation_report.json", report)
    registry_record = {
        "version": P14_LIVE_SCALED_APPROVAL_INTAKE_VERSION,
        "status": report["status"],
        "blocked": report["blocked"],
        "waiting": report["waiting"],
        "live_scaled_approval_valid_review_only": report["live_scaled_approval_valid_review_only"],
        "live_scaled_approval_packet_id": report.get("live_scaled_approval_packet_id"),
        "live_scaled_approval_intake_id": report.get("live_scaled_approval_intake_id"),
        "separate_runtime_enablement_step_required": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
        "report_sha256": report["p14_live_scaled_approval_intake_validation_sha256"],
    }
    registry_record = append_registry_record(
        registry_path(cfg, P14_LIVE_SCALED_APPROVAL_INTAKE_REGISTRY_NAME),
        registry_record,
        registry_name=P14_LIVE_SCALED_APPROVAL_INTAKE_REGISTRY_NAME,
        id_field="p14_live_scaled_approval_intake_validation_record_id",
        hash_field="p14_live_scaled_approval_intake_validation_registry_record_sha256",
        id_prefix="p14_live_scaled_approval_intake",
    )
    atomic_write_json(latest / "p14_live_scaled_approval_intake_validation_registry_record.json", registry_record)
    return report


__all__ = [
    "LIVE_SCALED_APPROVAL_PHRASE",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "STATUS_VALID_REVIEW_ONLY_NO_EXECUTION",
    "STATUS_WAITING_REVIEW_ONLY",
    "LiveScaledApprovalIntake",
    "LiveScaledApprovalPacket",
    "build_live_scaled_approval_intake_validation_report",
    "build_p14_negative_fixture_results",
    "build_review_only_live_scaled_approval_packet",
    "build_valid_live_scaled_approval_intake",
    "persist_live_scaled_approval_intake_validation",
]
