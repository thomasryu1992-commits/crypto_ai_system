from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.signed_testnet_probe_result_validator import (
    validate_read_only_venue_probe_result_summary,
)
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION = "step281_explicit_signed_testnet_execution_approval_packet_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP281 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP281 = False
SIGNED_TESTNET_PROMOTION_ALLOWED_BY_STEP281 = False
EXTERNAL_ORDER_SUBMISSION_ALLOWED_BY_STEP281 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP281 = False
PLACE_ORDER_ENABLED_BY_STEP281 = False
CANCEL_ORDER_ENABLED_BY_STEP281 = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP281 = False

_REQUIRED_OPERATOR_FIELDS = [
    "operator_id",
    "operator_role",
    "execution_ticket_id",
    "operator_signature",
    "timestamp_utc",
    "read_only_venue_probe_result_summary_id",
    "probe_result_summary_sha256",
    "full_regression_report_sha256",
]

_REQUIRED_RISK_FIELDS = [
    "risk_acceptance_id",
    "risk_approver_id",
    "risk_approver_role",
    "risk_acceptance_ticket_id",
    "risk_acceptance_signature",
    "timestamp_utc",
    "max_order_notional_usdt",
    "max_daily_order_count",
    "max_daily_loss_usdt",
    "max_consecutive_losses",
    "manual_kill_switch_required",
    "manual_kill_switch_active",
]

_REQUIRED_SCOPE_FIELDS = [
    "venue",
    "environment",
    "key_scope",
    "symbol",
    "allowed_order_types",
    "max_order_notional_usdt",
    "max_daily_order_count",
    "max_daily_loss_usdt",
    "max_consecutive_losses",
]


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k
        not in {
            "explicit_signed_testnet_execution_approval_packet_sha256",
            "created_at_utc",
            "approval_packet_path",
        }
    }


def _safe_float(value: Any, default: float = -1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validate_step280_full_regression_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(report or {})
    blockers: list[str] = []
    if data.get("step") != "step280_full_regression_runtime_hygiene":
        blockers.append("STEP281_FULL_REGRESSION_REPORT_STEP_INVALID")
    if data.get("status") not in {"passed", "passed_chunked_full_coverage"}:
        blockers.append("STEP281_FULL_REGRESSION_REPORT_STATUS_NOT_PASSED")
    if data.get("single_pytest_tests_command_replaced_in_ci") is not True:
        blockers.append("STEP281_FULL_REGRESSION_CHUNKED_CI_FLAG_MISSING")
    records = data.get("records") or []
    has_completed_records = isinstance(records, list) and bool(records)
    if _safe_int(data.get("chunked_full_regression_coverage_test_count"), 0) <= 0 and not has_completed_records:
        blockers.append("STEP281_FULL_REGRESSION_COVERAGE_TEST_COUNT_MISSING")
    if (
        _safe_int(data.get("focused_step258_280_test_count"), 0) <= 0
        and _safe_int(data.get("focused_step258_281_test_count"), 0) <= 0
        and not has_completed_records
    ):
        blockers.append("STEP281_FOCUSED_REGRESSION_TEST_COUNT_MISSING")
    for field in [
        "live_trading_enabled",
        "testnet_order_submission_allowed",
        "signed_testnet_promotion_allowed",
        "external_order_submission_performed",
        "settings_write_enabled",
        "score_weights_mutation_allowed",
    ]:
        if field in data and data.get(field) is not False:
            blockers.append(f"STEP281_FULL_REGRESSION_{field.upper()}_INVARIANT_FAILED")
    records = data.get("records") or []
    if not isinstance(records, list) or not records:
        blockers.append("STEP281_FULL_REGRESSION_RECORDS_MISSING")
    else:
        failed = [r.get("name") for r in records if isinstance(r, Mapping) and r.get("returncode") != 0]
        if failed:
            blockers.append("STEP281_FULL_REGRESSION_RECORD_FAILURE_PRESENT")
    payload = {
        "step": data.get("step"),
        "status": data.get("status"),
        "report_sha256": sha256_json(data),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    }
    return {
        "step280_full_regression_report_validation_id": stable_id("step281_full_regression_report_validation", payload),
        "valid": not blockers,
        "full_regression_report_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_step281_operator_execution_approval(
    operator_approval: Mapping[str, Any] | None,
    *,
    probe_result_summary: Mapping[str, Any] | None = None,
    full_regression_report_sha256: str | None = None,
) -> dict[str, Any]:
    data = dict(operator_approval or {})
    summary = dict(probe_result_summary or {})
    blockers: list[str] = []
    for field in _REQUIRED_OPERATOR_FIELDS:
        if not data.get(field):
            blockers.append(f"STEP281_OPERATOR_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("STEP281_OPERATOR_TIMESTAMP_NOT_CANONICAL_UTC")
    if summary:
        if data.get("read_only_venue_probe_result_summary_id") != summary.get("read_only_venue_probe_result_summary_id"):
            blockers.append("STEP281_OPERATOR_PROBE_SUMMARY_ID_MISMATCH")
        if data.get("probe_result_summary_sha256") != summary.get("probe_result_summary_sha256"):
            blockers.append("STEP281_OPERATOR_PROBE_SUMMARY_HASH_MISMATCH")
    if full_regression_report_sha256 and data.get("full_regression_report_sha256") != full_regression_report_sha256:
        blockers.append("STEP281_OPERATOR_FULL_REGRESSION_HASH_MISMATCH")
    if data.get("operator_acknowledges_execution_still_disabled") is not True:
        blockers.append("STEP281_OPERATOR_EXECUTION_DISABLED_ACK_MISSING")
    if data.get("operator_acknowledges_no_external_submission") is not True:
        blockers.append("STEP281_OPERATOR_NO_EXTERNAL_SUBMISSION_ACK_MISSING")
    if data.get("operator_acknowledges_place_order_disabled") is not True:
        blockers.append("STEP281_OPERATOR_PLACE_ORDER_DISABLED_ACK_MISSING")
    if data.get("operator_acknowledges_cancel_order_disabled") is not True:
        blockers.append("STEP281_OPERATOR_CANCEL_ORDER_DISABLED_ACK_MISSING")
    if _as_bool(data.get("operator_confirms_order_submission_enabled")):
        blockers.append("STEP281_OPERATOR_CONFIRMS_ORDER_SUBMISSION_ENABLED_BLOCKED")
    if _as_bool(data.get("operator_confirms_place_order_enabled")):
        blockers.append("STEP281_OPERATOR_CONFIRMS_PLACE_ORDER_ENABLED_BLOCKED")
    payload = {
        "operator_approval": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    }
    return {
        "operator_execution_approval_validation_id": stable_id("step281_operator_execution_approval_validation", payload),
        "valid": not blockers,
        "operator_execution_approval_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_manual_risk_acceptance(risk_acceptance: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(risk_acceptance or {})
    blockers: list[str] = []
    for field in _REQUIRED_RISK_FIELDS:
        if field not in data or data.get(field) in (None, ""):
            blockers.append(f"STEP281_RISK_ACCEPTANCE_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("STEP281_RISK_ACCEPTANCE_TIMESTAMP_NOT_CANONICAL_UTC")
    max_notional = _safe_float(data.get("max_order_notional_usdt"))
    max_orders = _safe_int(data.get("max_daily_order_count"))
    max_loss = _safe_float(data.get("max_daily_loss_usdt"))
    max_losses = _safe_int(data.get("max_consecutive_losses"))
    if max_notional <= 0 or max_notional > 5:
        blockers.append("STEP281_RISK_MAX_ORDER_NOTIONAL_OUT_OF_BOUNDS")
    if max_orders <= 0 or max_orders > 3:
        blockers.append("STEP281_RISK_MAX_DAILY_ORDER_COUNT_OUT_OF_BOUNDS")
    if max_loss <= 0 or max_loss > 10:
        blockers.append("STEP281_RISK_MAX_DAILY_LOSS_OUT_OF_BOUNDS")
    if max_losses <= 0 or max_losses > 2:
        blockers.append("STEP281_RISK_MAX_CONSECUTIVE_LOSSES_OUT_OF_BOUNDS")
    if data.get("manual_kill_switch_required") is not True:
        blockers.append("STEP281_RISK_MANUAL_KILL_SWITCH_REQUIRED_MISSING")
    if data.get("manual_kill_switch_active") is not False:
        blockers.append("STEP281_RISK_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED")
    if data.get("acknowledges_review_only_no_order_submission") is not True:
        blockers.append("STEP281_RISK_REVIEW_ONLY_NO_ORDER_SUBMISSION_ACK_MISSING")
    if data.get("acknowledges_testnet_scope_only") is not True:
        blockers.append("STEP281_RISK_TESTNET_SCOPE_ONLY_ACK_MISSING")
    payload = {
        "risk_acceptance": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    }
    return {
        "manual_risk_acceptance_validation_id": stable_id("step281_manual_risk_acceptance_validation", payload),
        "valid": not blockers,
        "manual_risk_acceptance_sha256": sha256_json(data),
        "risk_acceptance": data,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_testnet_execution_scope(scope: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(scope or {})
    blockers: list[str] = []
    for field in _REQUIRED_SCOPE_FIELDS:
        if field not in data or data.get(field) in (None, ""):
            blockers.append(f"STEP281_SCOPE_{field.upper()}_MISSING")
    environment = str(data.get("environment", "")).lower()
    key_scope = str(data.get("key_scope", "")).lower()
    if environment != "testnet":
        blockers.append("STEP281_SCOPE_ENVIRONMENT_NOT_TESTNET")
    if key_scope != "testnet":
        blockers.append("STEP281_SCOPE_KEY_SCOPE_NOT_TESTNET")
    base_url = str(data.get("base_url", "")).lower()
    if base_url and "testnet" not in base_url:
        blockers.append("STEP281_SCOPE_BASE_URL_NOT_TESTNET")
    if _as_bool(data.get("live_trading_enabled")) or _as_bool(data.get("allow_live_trading")):
        blockers.append("STEP281_SCOPE_LIVE_TRADING_ENABLED_BLOCKED")
    if _as_bool(data.get("place_order_enabled")):
        blockers.append("STEP281_SCOPE_PLACE_ORDER_ENABLED_BLOCKED")
    if _as_bool(data.get("testnet_order_submission_allowed")):
        blockers.append("STEP281_SCOPE_TESTNET_ORDER_SUBMISSION_ALLOWED_BLOCKED")
    max_notional = _safe_float(data.get("max_order_notional_usdt"))
    max_orders = _safe_int(data.get("max_daily_order_count"))
    max_loss = _safe_float(data.get("max_daily_loss_usdt"))
    max_losses = _safe_int(data.get("max_consecutive_losses"))
    if max_notional <= 0 or max_notional > 5:
        blockers.append("STEP281_SCOPE_MAX_ORDER_NOTIONAL_OUT_OF_BOUNDS")
    if max_orders <= 0 or max_orders > 3:
        blockers.append("STEP281_SCOPE_MAX_DAILY_ORDER_COUNT_OUT_OF_BOUNDS")
    if max_loss <= 0 or max_loss > 10:
        blockers.append("STEP281_SCOPE_MAX_DAILY_LOSS_OUT_OF_BOUNDS")
    if max_losses <= 0 or max_losses > 2:
        blockers.append("STEP281_SCOPE_MAX_CONSECUTIVE_LOSSES_OUT_OF_BOUNDS")
    payload = {
        "testnet_execution_scope": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    }
    return {
        "testnet_execution_scope_validation_id": stable_id("step281_testnet_execution_scope_validation", payload),
        "valid": not blockers,
        "testnet_execution_scope_sha256": sha256_json(data),
        "testnet_execution_scope": data,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def build_explicit_signed_testnet_execution_approval_packet(
    *,
    probe_result_summary: Mapping[str, Any],
    full_regression_report: Mapping[str, Any],
    operator_execution_approval: Mapping[str, Any],
    manual_risk_acceptance: Mapping[str, Any],
    testnet_execution_scope: Mapping[str, Any],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    summary = dict(probe_result_summary or {})
    full_report = dict(full_regression_report or {})
    blockers: list[str] = []

    summary_validation = validate_read_only_venue_probe_result_summary(summary)
    if summary_validation.get("valid") is not True:
        blockers.append("STEP281_PROBE_RESULT_SUMMARY_INVALID")
        blockers.extend(summary_validation.get("block_reasons", []))
    full_report_validation = _validate_step280_full_regression_report(full_report)
    if full_report_validation.get("valid") is not True:
        blockers.append("STEP281_FULL_REGRESSION_REPORT_INVALID")
        blockers.extend(full_report_validation.get("block_reasons", []))
    operator_validation = validate_step281_operator_execution_approval(
        operator_execution_approval,
        probe_result_summary=summary,
        full_regression_report_sha256=full_report_validation.get("full_regression_report_sha256"),
    )
    if operator_validation.get("valid") is not True:
        blockers.append("STEP281_OPERATOR_EXECUTION_APPROVAL_INVALID")
        blockers.extend(operator_validation.get("block_reasons", []))
    risk_validation = validate_manual_risk_acceptance(manual_risk_acceptance)
    if risk_validation.get("valid") is not True:
        blockers.append("STEP281_MANUAL_RISK_ACCEPTANCE_INVALID")
        blockers.extend(risk_validation.get("block_reasons", []))
    scope_validation = validate_testnet_execution_scope(testnet_execution_scope)
    if scope_validation.get("valid") is not True:
        blockers.append("STEP281_TESTNET_EXECUTION_SCOPE_INVALID")
        blockers.extend(scope_validation.get("block_reasons", []))

    # Step281 is an approval packet review stage only. It must not enable execution.
    packet_review_ready = not blockers
    id_payload = {
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
        "summary_id": summary.get("read_only_venue_probe_result_summary_id"),
        "summary_hash": summary.get("probe_result_summary_sha256"),
        "full_regression_hash": full_report_validation.get("full_regression_report_sha256"),
        "operator_hash": operator_validation.get("operator_execution_approval_sha256"),
        "risk_hash": risk_validation.get("manual_risk_acceptance_sha256"),
        "scope_hash": scope_validation.get("testnet_execution_scope_sha256"),
    }
    packet = {
        "explicit_signed_testnet_execution_approval_packet_id": stable_id("step281_signed_testnet_execution_approval_packet", id_payload),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
        "approval_stage": "explicit_signed_testnet_execution_approval_review_only_step281",
        "read_only_venue_probe_result_summary_id": summary.get("read_only_venue_probe_result_summary_id"),
        "probe_result_summary_sha256": summary.get("probe_result_summary_sha256"),
        "step280_full_regression_report_sha256": full_report_validation.get("full_regression_report_sha256"),
        "testnet_execution_session_id": summary.get("testnet_execution_session_id") or testnet_execution_scope.get("testnet_execution_session_id"),
        "probe_result_summary_validation": summary_validation,
        "step280_full_regression_report_validation": full_report_validation,
        "operator_execution_approval_validation": operator_validation,
        "manual_risk_acceptance_validation": risk_validation,
        "testnet_execution_scope_validation": scope_validation,
        "operator_execution_approval": dict(operator_execution_approval or {}),
        "manual_risk_acceptance": dict(manual_risk_acceptance or {}),
        "testnet_execution_scope": dict(testnet_execution_scope or {}),
        "packet_review_ready": packet_review_ready,
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP281,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP281,
        "signed_testnet_promotion_allowed": SIGNED_TESTNET_PROMOTION_ALLOWED_BY_STEP281,
        "external_order_submission_allowed": EXTERNAL_ORDER_SUBMISSION_ALLOWED_BY_STEP281,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP281,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP281,
        "cancel_order_enabled": CANCEL_ORDER_ENABLED_BY_STEP281,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP281,
        "order_submission_remains_disabled": True,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    packet["explicit_signed_testnet_execution_approval_packet_sha256"] = sha256_json(_payload_without_hash(packet))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        packet["approval_packet_path"] = str(path)
        packet["explicit_signed_testnet_execution_approval_packet_sha256"] = sha256_json(_payload_without_hash(packet))
        path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return packet


def validate_explicit_signed_testnet_execution_approval_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(packet or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION:
        blockers.append("STEP281_APPROVAL_PACKET_VERSION_INVALID")
    for field in [
        "explicit_signed_testnet_execution_approval_packet_id",
        "read_only_venue_probe_result_summary_id",
        "probe_result_summary_sha256",
        "step280_full_regression_report_sha256",
        "testnet_execution_session_id",
        "explicit_signed_testnet_execution_approval_packet_sha256",
    ]:
        if not data.get(field):
            blockers.append(f"STEP281_APPROVAL_PACKET_{field.upper()}_MISSING")
    for validation_field, reason in [
        ("probe_result_summary_validation", "STEP281_APPROVAL_PACKET_PROBE_SUMMARY_VALIDATION_INVALID"),
        ("step280_full_regression_report_validation", "STEP281_APPROVAL_PACKET_FULL_REGRESSION_VALIDATION_INVALID"),
        ("operator_execution_approval_validation", "STEP281_APPROVAL_PACKET_OPERATOR_VALIDATION_INVALID"),
        ("manual_risk_acceptance_validation", "STEP281_APPROVAL_PACKET_RISK_VALIDATION_INVALID"),
        ("testnet_execution_scope_validation", "STEP281_APPROVAL_PACKET_SCOPE_VALIDATION_INVALID"),
    ]:
        validation = data.get(validation_field) or {}
        if not isinstance(validation, Mapping) or validation.get("valid") is not True:
            blockers.append(reason)
            if isinstance(validation, Mapping):
                blockers.extend(validation.get("block_reasons") or [])
    if data.get("packet_review_ready") is not True:
        blockers.append("STEP281_APPROVAL_PACKET_NOT_REVIEW_READY")
    for field in [
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "signed_testnet_promotion_allowed",
        "external_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
    ]:
        if data.get(field) is not False:
            blockers.append(f"STEP281_APPROVAL_PACKET_{field.upper()}_INVARIANT_FAILED")
    if data.get("order_submission_remains_disabled") is not True:
        blockers.append("STEP281_APPROVAL_PACKET_ORDER_SUBMISSION_DISABLED_ACK_MISSING")
    if data.get("created_at_utc") and not is_canonical_utc_timestamp(data.get("created_at_utc")):
        blockers.append("STEP281_APPROVAL_PACKET_TIMESTAMP_NOT_CANONICAL_UTC")
    expected_hash = sha256_json(_payload_without_hash(data))
    if data.get("explicit_signed_testnet_execution_approval_packet_sha256") != expected_hash:
        blockers.append("STEP281_APPROVAL_PACKET_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "packet_id": data.get("explicit_signed_testnet_execution_approval_packet_id"),
        "packet_hash": data.get("explicit_signed_testnet_execution_approval_packet_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    }
    return {
        "explicit_signed_testnet_execution_approval_packet_validation_id": stable_id("step281_approval_packet_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
