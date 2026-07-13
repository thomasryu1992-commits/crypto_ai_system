from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import _find_secret_like_values, _safe_bool

PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_VERSION = "phase9_2_single_testnet_runtime_submit_wrapper_v1"
PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_REGISTRY_NAME = "phase9_2_single_testnet_runtime_submit_wrapper_registry"
STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_RECORDED_MOCK_DEFAULT = "PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_RECORDED_MOCK_DEFAULT_REVIEW_ONLY"
STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_BLOCKED = "PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_BLOCKED_FAIL_CLOSED"
STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_MOCK_SUBMITTED = "PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_MOCK_SUBMITTED_REVIEW_ONLY"

APPROVAL_TEXT_EN = "I explicitly approve Phase 9.2 single signed TESTNET order submission only."
APPROVAL_TEXT_KO = "Phase 9.2 단일 signed TESTNET 주문 제출을 명시적으로 승인합니다."

SOURCE_FILES = {
    "runtime_submit_action_boundary": "phase9_2_runtime_submit_action_boundary_report.json",
    "manual_final_confirmation": "phase9_2_manual_final_confirmation_report.json",
    "final_approval_package": "phase9_2_final_approval_package_report.json",
    "evidence_intake": "phase9_10_signed_testnet_evidence_intake_report.json",
}

RUNTIME_FALSE_FLAGS = sorted(set(FALSE_FLAGS + [
    "runtime_authority_granted",
    "runtime_authority_application_performed",
    "secret_manager_runtime_binding_performed",
    "executor_policy_application_performed",
    "endpoint_policy_application_performed",
    "endpoint_policy_changed",
    "testnet_order_submission_allowed",
    "signed_order_executor_enabled",
    "place_order_enabled",
    "cancel_order_enabled",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_testnet_order_submit_may_begin",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "real_order_id_created",
    "real_order_submit_attempted",
    "order_endpoint_call_allowed",
    "order_status_endpoint_call_allowed",
    "cancel_endpoint_call_allowed",
    "http_request_allowed",
    "signature_creation_allowed",
    "signed_request_creation_allowed",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "live_order_submission_performed",
    "mainnet_order_submission_performed",
    "withdrawal_permission_used",
    "transfer_permission_used",
]))

POST_ACTION_RELOCK_FLAGS = {
    "place_order_enabled_after_action": False,
    "cancel_order_enabled_after_action": False,
    "signed_order_executor_enabled_after_action": False,
    "testnet_order_submission_allowed_after_action": False,
    "order_endpoint_call_allowed_after_action": False,
    "signature_creation_allowed_after_action": False,
    "http_request_allowed_after_action": False,
}


@dataclass(frozen=True)
class RuntimeSubmitIntent:
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: str = "0.001"
    max_notional: float = 10.0
    testnet_only: bool = True
    max_order_count: int = 1
    approval_text: str = ""
    key_ref: str = "metadata_only_testnet_key_ref"
    key_fingerprint_sha256: str = ""
    confirm_real_testnet_submit: bool = False
    allow_mock_submit: bool = True
    fresh_endpoint_time_risk_refresh_passed: bool = False
    kill_switch_confirmed: bool = False


class MockSingleTestnetExchangeAdapter:
    """Deterministic mock adapter. It never signs, sends HTTP, or calls an exchange."""

    adapter_id = "mock_single_testnet_exchange_adapter_v1"
    real_endpoint_adapter = False

    def submit_order(self, intent: RuntimeSubmitIntent, *, idempotency_key: str) -> dict[str, Any]:
        client_order_id = stable_id("mock_client_order", {
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "idempotency_key": idempotency_key,
        }, 20)
        exchange_order_id = stable_id("mock_exchange_order", {"client_order_id": client_order_id}, 20)
        payload = {
            "adapter_id": self.adapter_id,
            "mock_response": True,
            "real_endpoint_adapter": False,
            "exchange": "mock_testnet",
            "symbol": intent.symbol,
            "side": intent.side,
            "order_type": intent.order_type,
            "quantity": intent.quantity,
            "status": "MOCK_ACCEPTED",
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "idempotency_key": idempotency_key,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "private_key_logged": False,
            "passphrase_logged": False,
            "signature_created": False,
            "signed_request_created": False,
            "http_request_sent": False,
            "order_endpoint_called": False,
        }
        payload["mock_response_sha256"] = sha256_json(payload)
        return payload


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


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in RUNTIME_FALSE_FLAGS}


def _unsafe_true_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in RUNTIME_FALSE_FLAGS if _safe_bool(data.get(field)))


def _hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_runtime_submit_action_boundary_report_sha256",
        "phase9_2_manual_final_confirmation_report_sha256",
        "phase9_2_final_approval_package_report_sha256",
        "phase9_10_signed_testnet_evidence_intake_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_true_fields(data):
        return False
    if name == "runtime_submit_action_boundary":
        return (
            data.get("runtime_submit_action_ready_for_explicit_submit_approval_review_only") is True
            and data.get("runtime_submit_action_approved") is False
            and data.get("runtime_submit_action_executed") is False
            and data.get("actual_order_submission_performed") is False
        )
    if name == "manual_final_confirmation":
        return data.get("manual_final_confirmation_valid") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "final_approval_package":
        return data.get("final_approval_packet_valid") is True and data.get("phase9_2_order_submission_authorized") is False
    if name == "evidence_intake":
        return (
            data.get("phase9_2_execution_evidence_template_ready") is True
            and data.get("phase9_10_evidence_templates_valid") is True
            and data.get("actual_order_submission_performed") is False
        )
    return True


def validate_explicit_approval_text(text: str) -> dict[str, Any]:
    normalized = " ".join(str(text or "").split())
    approved = APPROVAL_TEXT_EN in normalized or APPROVAL_TEXT_KO in normalized
    live_denied = "live/mainnet" in normalized.lower() or "live" in normalized.lower() and "mainnet" in normalized.lower() or "live/mainnet 주문은 승인하지 않습니다" in normalized
    one_order = "one order" in normalized.lower() or "단일 주문 1개" in normalized or "1개" in normalized
    testnet = "testnet" in normalized.lower() or "TESTNET" in normalized
    return {
        "explicit_approval_text_present": bool(normalized),
        "explicit_approval_text_valid": bool(approved and testnet and one_order),
        "approval_text_mentions_testnet": bool(testnet),
        "approval_text_limits_one_order": bool(one_order),
        "approval_text_denies_live_mainnet": bool(live_denied),
        "approval_text_hash_sha256": sha256_json({"approval_text": normalized}) if normalized else None,
        "approval_text_stored_redacted": bool(normalized),
    }


def build_runtime_submit_wrapper_template(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    sources = {name: _read_latest_json(cfg, filename) for name, filename in SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if payload and not _source_ready(name, payload)]
    template_id = stable_id("phase9_2_single_testnet_runtime_submit_wrapper", source_summary, 24)
    payload = {
        "artifact_type": "phase9_2_single_testnet_runtime_submit_wrapper_template_review_only",
        "phase9_2_single_testnet_runtime_submit_wrapper_id": template_id,
        "phase9_2_single_testnet_runtime_submit_wrapper_version": PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_VERSION,
        "status": STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_RECORDED_MOCK_DEFAULT,
        "review_only": True,
        "mocked_by_default": True,
        "real_endpoint_call_default_allowed": False,
        "real_endpoint_adapter_implemented": False,
        "source_evidence_hash_summary": source_summary,
        "missing_required_sources": missing,
        "required_sources_not_ready": not_ready,
        "action_scope": "phase9_2_single_signed_testnet_order_runtime_submit_wrapper_one_order_only",
        "testnet_only": True,
        "max_order_count": 1,
        "single_order_scope": True,
        "small_notional_required": True,
        "fresh_endpoint_time_risk_refresh_required_at_action_time": True,
        "explicit_runtime_submit_approval_text_required": True,
        "runtime_secret_binding_required_at_action_time": True,
        "metadata_only_key_fingerprint_required": True,
        "duplicate_submit_lock_required": True,
        "post_action_relock_required": True,
        "allowed_modes": ["dry_run", "mock_submit"],
        "disallowed_modes": ["live", "mainnet", "auto_trading", "multi_order"],
        **_disabled_payload(),
        **POST_ACTION_RELOCK_FLAGS,
        "mock_order_submission_performed": False,
        "dry_run_performed": False,
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_single_testnet_runtime_submit_wrapper_template_sha256"] = sha256_json(payload)
    return payload


def validate_runtime_submit_wrapper_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    unsafe = _unsafe_true_fields(data)
    secret_like = _find_secret_like_values(data)
    errors: list[str] = []
    if data.get("testnet_only") is not True:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_REQUIRES_TESTNET_ONLY")
    if int(data.get("max_order_count") or 0) != 1:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_REQUIRES_MAX_ORDER_COUNT_ONE")
    if data.get("real_endpoint_call_default_allowed") is not False:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_DEFAULT_ENDPOINT_CALL_MUST_BE_FALSE")
    if data.get("real_endpoint_adapter_implemented") is not False:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_REAL_ENDPOINT_ADAPTER_NOT_ALLOWED_IN_THIS_PACKAGE")
    if unsafe:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe))
    if secret_like:
        errors.append("PHASE9_2_RUNTIME_SUBMIT_WRAPPER_SECRET_LIKE_VALUES_PRESENT")
    return {
        "artifact_type": "phase9_2_single_testnet_runtime_submit_wrapper_validation_report",
        "phase9_2_single_testnet_runtime_submit_wrapper_version": PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_VERSION,
        "blocked": bool(errors),
        "fail_closed": bool(errors),
        "review_only": True,
        "wrapper_payload_valid": not errors,
        "unsafe_true_fields": unsafe,
        "secret_like_values_detected": bool(secret_like),
        "block_reasons": errors,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": utc_now_canonical(),
    }


def build_submit_intent_from_env_and_args(**kwargs: Any) -> RuntimeSubmitIntent:
    return RuntimeSubmitIntent(
        symbol=str(kwargs.get("symbol") or os.environ.get("CAS_SUBMIT_SYMBOL") or "BTCUSDT"),
        side=str(kwargs.get("side") or os.environ.get("CAS_SUBMIT_SIDE") or "BUY"),
        order_type=str(kwargs.get("order_type") or os.environ.get("CAS_SUBMIT_ORDER_TYPE") or "MARKET"),
        quantity=str(kwargs.get("quantity") or os.environ.get("CAS_SUBMIT_QUANTITY") or "0.001"),
        max_notional=float(kwargs.get("max_notional") or os.environ.get("CAS_SUBMIT_MAX_NOTIONAL") or 10.0),
        approval_text=str(kwargs.get("approval_text") or os.environ.get("CAS_PHASE9_2_RUNTIME_APPROVAL_TEXT") or ""),
        key_ref=str(kwargs.get("key_ref") or os.environ.get("CAS_TESTNET_KEY_REF") or "metadata_only_testnet_key_ref"),
        key_fingerprint_sha256=str(kwargs.get("key_fingerprint_sha256") or os.environ.get("CAS_TESTNET_KEY_FINGERPRINT_SHA256") or ""),
        confirm_real_testnet_submit=bool(kwargs.get("confirm_real_testnet_submit", False)),
        allow_mock_submit=bool(kwargs.get("allow_mock_submit", True)),
        fresh_endpoint_time_risk_refresh_passed=bool(kwargs.get("fresh_endpoint_time_risk_refresh_passed", False)),
        kill_switch_confirmed=bool(kwargs.get("kill_switch_confirmed", False)),
    )


def _validate_runtime_controls(intent: RuntimeSubmitIntent) -> list[str]:
    blockers: list[str] = []
    approval = validate_explicit_approval_text(intent.approval_text)
    if not intent.confirm_real_testnet_submit:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_CONFIRM_REAL_TESTNET_SUBMIT_FLAG_NOT_PRESENT")
    if not approval["explicit_approval_text_valid"]:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_EXPLICIT_APPROVAL_TEXT_INVALID_OR_MISSING")
    if intent.testnet_only is not True:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_REQUIRES_TESTNET_ONLY")
    if int(intent.max_order_count) != 1:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_REQUIRES_MAX_ORDER_COUNT_ONE")
    if float(intent.max_notional) > 10.0:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_MAX_NOTIONAL_EXCEEDS_SMALL_SCOPE")
    if not intent.key_fingerprint_sha256 or len(intent.key_fingerprint_sha256) != 64:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_TESTNET_KEY_FINGERPRINT_MISSING_OR_INVALID")
    if not intent.fresh_endpoint_time_risk_refresh_passed:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_FRESH_ENDPOINT_TIME_RISK_REFRESH_NOT_PASSED")
    if not intent.kill_switch_confirmed:
        blockers.append("PHASE9_2_RUNTIME_SUBMIT_KILL_SWITCH_NOT_CONFIRMED")
    return blockers


def run_phase9_2_single_testnet_runtime_submit_wrapper(
    *,
    cfg: AppConfig | None = None,
    intent: RuntimeSubmitIntent | None = None,
    adapter: MockSingleTestnetExchangeAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config()
    intent = intent or build_submit_intent_from_env_and_args()
    adapter = adapter or MockSingleTestnetExchangeAdapter()
    created_at = utc_now_canonical()
    template = build_runtime_submit_wrapper_template(cfg=cfg, created_at_utc=created_at)
    template_validation = validate_runtime_submit_wrapper_payload(template)
    approval_validation = validate_explicit_approval_text(intent.approval_text)
    runtime_blockers = _validate_runtime_controls(intent)

    idempotency_key = stable_id("phase9_2_one_order_idempotency", {
        "symbol": intent.symbol,
        "side": intent.side,
        "quantity": intent.quantity,
        "approval_hash": approval_validation.get("approval_text_hash_sha256"),
        "created_at_utc": created_at,
    }, 24)

    mock_response: dict[str, Any] | None = None
    mock_submit_performed = False
    dry_run_performed = True
    if not runtime_blockers and intent.allow_mock_submit:
        # This intentionally uses the deterministic mock adapter. No signature, HTTP, or exchange endpoint is used.
        mock_response = adapter.submit_order(intent, idempotency_key=idempotency_key)
        mock_submit_performed = True
        dry_run_performed = False

    status = STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_MOCK_SUBMITTED if mock_submit_performed else STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_BLOCKED
    report = {
        "artifact_type": "phase9_2_single_testnet_runtime_submit_wrapper_report",
        "phase9_2_single_testnet_runtime_submit_wrapper_version": PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_VERSION,
        "status": status,
        "blocked": bool(runtime_blockers),
        "fail_closed": bool(runtime_blockers),
        "review_only": True,
        "mocked_by_default": True,
        "real_endpoint_adapter_implemented": False,
        "real_exchange_endpoint_call_performed": False,
        "runtime_submit_wrapper_ready": template_validation["wrapper_payload_valid"],
        "runtime_controls_valid_for_mock_submit": not runtime_blockers,
        "runtime_controls_block_reasons": runtime_blockers,
        "approval_validation": approval_validation,
        "idempotency_key": idempotency_key,
        "duplicate_submit_lock_acquired_for_mock_only": bool(mock_submit_performed),
        "adapter_id": getattr(adapter, "adapter_id", "unknown_adapter"),
        "symbol": intent.symbol,
        "side": intent.side,
        "order_type": intent.order_type,
        "quantity": intent.quantity,
        "max_notional": intent.max_notional,
        "testnet_only": True,
        "max_order_count": 1,
        "key_ref": intent.key_ref,
        "key_fingerprint_sha256": intent.key_fingerprint_sha256 if intent.key_fingerprint_sha256 else None,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "private_key_logged": False,
        "passphrase_logged": False,
        "secret_file_read": False,
        "secret_file_created": False,
        **_disabled_payload(),
        **POST_ACTION_RELOCK_FLAGS,
        "mock_order_submission_performed": bool(mock_submit_performed),
        "dry_run_performed": bool(dry_run_performed),
        "mock_exchange_response_redacted": mock_response,
        "next_action_if_real_submit_later": "run_phase9_3_status_polling_after_real_order_id_exists",
        "created_at_utc": created_at,
    }
    report["phase9_2_single_testnet_runtime_submit_wrapper_report_sha256"] = sha256_json(report)
    return report, template


def build_negative_fixture_results() -> dict[str, Any]:
    base = build_runtime_submit_wrapper_template()
    fixtures = {
        "actual_order_submission_true": {**base, "actual_order_submission_performed": True},
        "order_endpoint_called_true": {**base, "order_endpoint_called": True},
        "signature_created_true": {**base, "signature_created": True},
        "real_endpoint_adapter_true": {**base, "real_endpoint_adapter_implemented": True},
        "max_order_count_two": {**base, "max_order_count": 2},
        "secret_like_value": {**base, "api_secret": "SECRET_VALUE_SHOULD_NOT_APPEAR"},
    }
    results: dict[str, Any] = {}
    for name, payload in fixtures.items():
        validation = validate_runtime_submit_wrapper_payload(payload)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    output = {
        "artifact_type": "phase9_2_single_testnet_runtime_submit_wrapper_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_single_testnet_runtime_submit_wrapper_negative_fixture_results_sha256"] = sha256_json(output)
    return output


def persist_phase9_2_single_testnet_runtime_submit_wrapper(
    *,
    cfg: AppConfig | None = None,
    intent: RuntimeSubmitIntent | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    report, template = run_phase9_2_single_testnet_runtime_submit_wrapper(cfg=cfg, intent=intent)
    validation = validate_runtime_submit_wrapper_payload(template)
    negative = build_negative_fixture_results()

    files = {
        "phase9_2_single_testnet_runtime_submit_WRAPPER_MOCK_DEFAULT_REVIEW_ONLY.json": template,
        "phase9_2_single_testnet_runtime_submit_wrapper_validation_report.json": validation,
        "phase9_2_single_testnet_runtime_submit_wrapper_report.json": report,
        "phase9_2_single_testnet_runtime_submit_negative_fixture_results.json": negative,
    }
    for name, payload in files.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(signed_testnet / name, payload)

    handoff = "\n".join([
        "# Phase 9.2 Single Testnet Runtime Submit Wrapper / Mocked by Default",
        "",
        "This package creates a narrow one-order runtime submit wrapper but keeps the default path mocked/review-only.",
        "No real exchange endpoint is called by this package.",
        "API key values, API secrets, private keys, passphrases, and secret files must not be included.",
        "The wrapper requires explicit approval text, one-order scope, testnet-only scope, fresh risk refresh, kill switch confirmation, and metadata-only key fingerprint before mock-submit evidence can be produced.",
        "Real endpoint wiring remains a separate operator action and is not implemented here.",
    ])
    (latest / "PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_HANDOFF_MOCK_DEFAULT_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    record = append_registry_record(
        registry_path(cfg, PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_REGISTRY_NAME),
        {
            "artifact_type": "phase9_2_single_testnet_runtime_submit_wrapper_registry_record",
            "status": report["status"],
            "review_only": True,
            "mocked_by_default": True,
            "real_exchange_endpoint_call_performed": False,
            "report_sha256": report["phase9_2_single_testnet_runtime_submit_wrapper_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_REGISTRY_NAME,
        id_field="phase9_2_single_testnet_runtime_submit_wrapper_registry_id",
        hash_field="phase9_2_single_testnet_runtime_submit_wrapper_registry_record_sha256",
        id_prefix="phase9_2_single_testnet_runtime_submit_wrapper_registry",
    )
    atomic_write_json(latest / "phase9_2_single_testnet_runtime_submit_wrapper_registry_record.json", record)
    return report
