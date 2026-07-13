from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VERSION = "phase9_2_separate_one_order_runtime_submit_approval_packet_v1"
PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_REGISTRY_NAME = "phase9_2_separate_one_order_runtime_submit_approval_packet_registry"
STATUS_AWAITING_APPROVAL = "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_AWAITING_OPERATOR_FILLED_APPROVAL_REVIEW_ONLY"
STATUS_VALIDATED_REVIEW_ONLY = "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VALIDATED_REVIEW_ONLY_NO_ORDER_SUBMIT"
STATUS_BLOCKED = "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_BLOCKED_FAIL_CLOSED"

APPROVAL_TEXT_EN = "I explicitly approve Phase 9.2 single signed TESTNET order submission only."
APPROVAL_TEXT_KO = "Phase 9.2 단일 signed TESTNET 주문 제출을 명시적으로 승인합니다."

FILLED_APPROVAL_FILENAME = "phase9_2_separate_one_order_runtime_submit_APPROVAL_FILLED_REVIEW_ONLY.json"
TEMPLATE_FILENAME = "phase9_2_separate_one_order_runtime_submit_APPROVAL_TEMPLATE_REVIEW_ONLY.json"

EXECUTION_FALSE_FLAGS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_authority_granted",
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_order_runtime_submit_approval_granted",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_exchange_endpoint_call_performed",
    "real_testnet_order_endpoint_called",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "executor_enable_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
]


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


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in EXECUTION_FALSE_FLAGS}


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def build_approval_template(*, created_at_utc: str | None = None) -> dict[str, Any]:
    created_at_utc = created_at_utc or utc_now_canonical()
    template = {
        "artifact_type": "phase9_2_separate_one_order_runtime_submit_approval_template",
        "review_only": True,
        "no_order_submit": True,
        "phase": "9.2",
        "approval_scope": "single_signed_testnet_order_only",
        "approval_text_required_en": APPROVAL_TEXT_EN,
        "approval_text_required_ko": APPROVAL_TEXT_KO,
        "operator_approval_text": "",
        "operator_name_or_handle": "",
        "approved_at_utc": "",
        "symbol": "BTCUSDT",
        "venue": "binance_futures_testnet",
        "testnet_only": True,
        "live_or_mainnet_approved": False,
        "one_order_only": True,
        "max_order_count": 1,
        "max_notional_usdt": 10.0,
        "no_live_mainnet_order_approved": True,
        "fresh_hot_path_risk_refresh_required_at_action_time": True,
        "runtime_secret_binding_required_at_action_time": True,
        "metadata_only_secret_evidence_in_artifacts": True,
        "duplicate_submit_lock_required": True,
        "post_submit_immediate_relock_required": True,
        "status_polling_reconciliation_split_to_phase9_3_9_4": True,
        "does_not_enable_submit_by_itself": True,
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    template["phase9_2_separate_one_order_runtime_submit_approval_template_sha256"] = sha256_json(template)
    return template


def validate_operator_filled_approval(payload: Mapping[str, Any], *, metadata_ready: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    text = str(payload.get("operator_approval_text", ""))
    if APPROVAL_TEXT_EN not in text and APPROVAL_TEXT_KO not in text:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_REQUIRED_EXPLICIT_APPROVAL_TEXT_MISSING")
    lowered = text.lower()
    if "testnet" not in lowered and "TESTNET" not in text:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_TESTNET_SCOPE_MISSING")
    if "live" not in lowered and "mainnet" not in lowered:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_LIVE_MAINNET_DENIAL_MISSING")
    if not _is_true(payload.get("testnet_only")):
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_TESTNET_ONLY_NOT_TRUE")
    if _is_true(payload.get("live_or_mainnet_approved")):
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_LIVE_OR_MAINNET_APPROVED_BLOCKED")
    if not _is_true(payload.get("one_order_only")) or int(payload.get("max_order_count", 0) or 0) != 1:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_MAX_ORDER_COUNT_NOT_ONE")
    if str(payload.get("symbol", "")).upper() != "BTCUSDT":
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_SYMBOL_NOT_BTCUSDT")
    try:
        max_notional = float(payload.get("max_notional_usdt", 0) or 0)
    except (TypeError, ValueError):
        max_notional = 0.0
    if max_notional <= 0 or max_notional > 10:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_MAX_NOTIONAL_INVALID_OR_ABOVE_10_USDT")
    required_true_fields = [
        "no_live_mainnet_order_approved",
        "fresh_hot_path_risk_refresh_required_at_action_time",
        "runtime_secret_binding_required_at_action_time",
        "metadata_only_secret_evidence_in_artifacts",
        "duplicate_submit_lock_required",
        "post_submit_immediate_relock_required",
        "status_polling_reconciliation_split_to_phase9_3_9_4",
        "does_not_enable_submit_by_itself",
    ]
    for field in required_true_fields:
        if not _is_true(payload.get(field)):
            reasons.append(f"PHASE9_2_ONE_ORDER_APPROVAL_REQUIRED_FIELD_NOT_TRUE:{field}")
    unsafe_true = [field for field in EXECUTION_FALSE_FLAGS if _is_true(payload.get(field))]
    if unsafe_true:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_UNSAFE_TRUE_FLAGS:" + ",".join(sorted(unsafe_true)))
    if not metadata_ready:
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_PUBLIC_METADATA_CONDITIONS_NOT_READY")
    if not str(payload.get("operator_name_or_handle", "")).strip():
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_OPERATOR_IDENTITY_MISSING")
    if not str(payload.get("approved_at_utc", "")).strip():
        reasons.append("PHASE9_2_ONE_ORDER_APPROVAL_APPROVED_AT_UTC_MISSING")
    return (not reasons, reasons)


def build_phase9_2_separate_one_order_runtime_submit_approval_packet(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    latest = _latest_dir(cfg)
    bridge_report = _read_latest_json(cfg, "phase9_2_public_metadata_probe_bridge_report.json")
    filled_validation_report = _read_latest_json(cfg, "phase9_2_public_metadata_probe_result_filled_validation_report.json")
    final_checklist = _read_latest_json(cfg, "phase9_2_final_pre_submit_checklist_report.json")
    metadata_ready = bool(
        bridge_report.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True
        and (
            filled_validation_report.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True
            or filled_validation_report.get("operator_filled_public_metadata_probe_result_validated") is True
        )
    )
    final_checklist_ready = bool(final_checklist.get("ready_for_separate_one_order_runtime_approval_review_only") is True or metadata_ready)
    filled_path = latest / FILLED_APPROVAL_FILENAME
    filled_present = filled_path.exists()
    filled_payload = _read_latest_json(cfg, FILLED_APPROVAL_FILENAME) if filled_present else {}
    approval_valid, approval_reasons = validate_operator_filled_approval(filled_payload, metadata_ready=bool(metadata_ready and final_checklist_ready)) if filled_present else (False, ["PHASE9_2_ONE_ORDER_APPROVAL_FILLED_APPROVAL_PACKET_MISSING"])

    blockers = list(approval_reasons)
    if not metadata_ready:
        blockers.append("PHASE9_2_ONE_ORDER_APPROVAL_METADATA_BRIDGE_OR_FILLED_VALIDATION_NOT_READY")
    if not final_checklist_ready:
        blockers.append("PHASE9_2_ONE_ORDER_APPROVAL_FINAL_PRE_SUBMIT_CHECKLIST_NOT_READY")

    report_id = stable_id("phase9_2_separate_one_order_runtime_submit_approval_packet", {
        "metadata_ready": metadata_ready,
        "final_checklist_ready": final_checklist_ready,
        "filled_present": filled_present,
        "approval_valid": approval_valid,
        "version": PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VERSION,
    }, 24)
    status = STATUS_VALIDATED_REVIEW_ONLY if approval_valid and metadata_ready and final_checklist_ready else (STATUS_AWAITING_APPROVAL if not filled_present else STATUS_BLOCKED)
    report: dict[str, Any] = {
        "artifact_type": "phase9_2_separate_one_order_runtime_submit_approval_packet_report",
        "phase9_2_separate_one_order_runtime_submit_approval_packet_id": report_id,
        "phase9_2_separate_one_order_runtime_submit_approval_packet_version": PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VERSION,
        "status": status,
        "blocked": not approval_valid,
        "fail_closed": not approval_valid,
        "review_only": True,
        "no_order_submit": True,
        "phase": "9.2",
        "operator_filled_approval_present": filled_present,
        "operator_filled_approval_validated": approval_valid,
        "public_metadata_conditions_ready_for_submit_review_only": metadata_ready,
        "final_pre_submit_checklist_ready_for_separate_approval_review_only": final_checklist_ready,
        "ready_for_one_order_runtime_submit_operator_review_only": bool(approval_valid and metadata_ready and final_checklist_ready),
        "approval_text_required_en": APPROVAL_TEXT_EN,
        "approval_text_required_ko": APPROVAL_TEXT_KO,
        "approved_scope": {
            "testnet_only": True,
            "venue": "binance_futures_testnet",
            "symbol": "BTCUSDT",
            "one_order_only": True,
            "max_order_count": 1,
            "max_notional_usdt": 10.0,
            "live_or_mainnet_approved": False,
        },
        "runtime_action_requirements": {
            "fresh_hot_path_risk_refresh_required_at_action_time": True,
            "runtime_secret_binding_required_at_action_time": True,
            "metadata_only_secret_evidence_in_artifacts": True,
            "duplicate_submit_lock_required": True,
            "post_submit_immediate_relock_required": True,
            "status_polling_reconciliation_split_to_phase9_3_9_4": True,
            "operator_local_execution_required": True,
        },
        "real_testnet_submit_may_begin": False,
        "phase9_2_order_submission_authorized": False,
        "phase9_2_single_order_runtime_submit_approval_granted": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "secret_value_accessed": False,
        "executor_enable_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "block_reasons": blockers,
        "next_action": "operator_fills_approval_packet_after_review_or_proceed_to_runtime_submit_wrapper_only_after_separate_explicit_approval_and_fresh_risk_refresh",
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_separate_one_order_runtime_submit_approval_packet_report_sha256"] = sha256_json(report)
    return report


def persist_phase9_2_separate_one_order_runtime_submit_approval_packet(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_phase9_2_separate_one_order_runtime_submit_approval_packet(cfg=cfg, created_at_utc=created_at_utc)
    template = build_approval_template(created_at_utc=created_at_utc or report["created_at_utc"])
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    handoff = "\n".join([
        "# Phase 9.2 Separate One-Order Runtime Submit Approval Packet / No Order Submit",
        "",
        "This packet prepares a separate explicit operator approval record for exactly one signed testnet order.",
        "It does not submit orders, call order/private endpoints, create signatures, read secrets, enable executors, or mutate runtime settings.",
        "A validated approval packet is review evidence only; runtime submit remains false until an operator-local action-time guard separately runs.",
    ])
    for directory in (latest, signed_testnet):
        atomic_write_json(directory / "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json", report)
        atomic_write_json(directory / TEMPLATE_FILENAME, template)
        (directory / "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_separate_one_order_runtime_submit_approval_packet_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "sha256": report["phase9_2_separate_one_order_runtime_submit_approval_packet_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_REGISTRY_NAME,
        id_field="phase9_2_separate_one_order_runtime_submit_approval_packet_registry_id",
        hash_field="phase9_2_separate_one_order_runtime_submit_approval_packet_registry_record_sha256",
        id_prefix="phase9_2_separate_one_order_runtime_submit_approval_packet_registry",
    )
    atomic_write_json(latest / "phase9_2_separate_one_order_runtime_submit_approval_packet_registry_record.json", record)
    return report


def build_negative_fixture_results() -> dict[str, Any]:
    good = build_approval_template(created_at_utc="2026-01-01T00:00:00Z")
    good.update({
        "operator_approval_text": "Phase 9.2 단일 signed TESTNET 주문 제출을 명시적으로 승인합니다. 범위는 testnet 단일 주문 1개로 제한합니다. 심볼은 BTCUSDT testnet only입니다. 최대 주문 금액은 10 USDT입니다. live/mainnet 주문은 승인하지 않습니다. testnet order endpoint가 1회 호출될 수 있음을 이해합니다.",
        "operator_name_or_handle": "operator_fixture",
        "approved_at_utc": "2026-01-01T00:00:00Z",
    })
    fixtures = {
        "missing_text": {**good, "operator_approval_text": "approve"},
        "mainnet_allowed": {**good, "live_or_mainnet_approved": True},
        "multi_order": {**good, "max_order_count": 2},
        "max_notional_above_cap": {**good, "max_notional_usdt": 11.0},
        "unsafe_order_endpoint_true": {**good, "order_endpoint_called": True},
        "metadata_not_ready": good,
    }
    results = {}
    for name, payload in fixtures.items():
        metadata_ready = name != "metadata_not_ready"
        valid, reasons = validate_operator_filled_approval(payload, metadata_ready=metadata_ready)
        results[name] = {"fixture_name": name, "blocked": not valid, "fail_closed": not valid, "block_reasons": reasons}
    output = {
        "artifact_type": "phase9_2_separate_one_order_runtime_submit_approval_packet_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_separate_one_order_runtime_submit_approval_packet_negative_fixture_results_sha256"] = sha256_json(output)
    return output
