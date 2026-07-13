from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from crypto_ai_system.utils.audit import sha256_json, sha256_text, utc_now_canonical

P68_VERSION = "p68_real_order_test_operator_run_package_v1"
STATUS_P68_READY = "P68_REAL_ORDER_TEST_OPERATOR_RUN_PACKAGE_READY_REVIEW_ONLY_NO_CALL"
STATUS_P68_VALIDATED = "P68_REAL_ORDER_TEST_OPERATOR_RUN_PACKAGE_VALIDATED_REVIEW_ONLY_NO_CALL"
STATUS_P68_BLOCKED = "P68_REAL_ORDER_TEST_OPERATOR_RUN_PACKAGE_BLOCKED_FAIL_CLOSED"
P65_SOURCE_STATUS = "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_VALIDATED_REVIEW_ONLY_DISABLED"
P66_SOURCE_STATUS = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_READY_REVIEW_ONLY_NO_CALL"
P67_SOURCE_STATUS = "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_READY_REVIEW_ONLY_NO_SUBMIT"
EXACT_OPERATOR_PHRASE = "AUTHORIZE ONE P65 BINANCE FUTURES TESTNET ORDER TEST SENDER EXECUTABLE RUN ONLY"
ALLOWED_VENUE = "binance_futures_testnet"
ALLOWED_BASE_URL = "https://demo-fapi.binance.com"
ALLOWED_METHOD = "POST"
ALLOWED_PATH = "/fapi/v1/order/test"
ALLOWED_SYMBOL = "BTCUSDT"
P68_TEMPLATE_SCOPE = "p68_operator_run_package_template_only"
P68_ACTUAL_RUN_HANDOFF_SCOPE = "p68_operator_managed_external_order_test_run_handoff_only"
P68_REGISTRY_NAME = "p68_real_order_test_operator_run_package_registry"

FORBIDDEN_KEY_TOKENS = (
    "api_key_value", "api_secret_value", "secret_value", "private_key", "passphrase",
    "raw_secret", "credential_value", "secret_file_contents", "raw_signed_payload",
    "raw_request_body", "raw_response_body", "authorization_header", "x-mbx-apikey",
)
FORBIDDEN_VALUE_TOKENS = (
    "-----BEGIN PRIVATE KEY-----", "api_secret=", "api_key=", "x-mbx-apikey:", "authorization: bearer ",
)


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _is_nonzero_sha256(value: Any) -> bool:
    return _is_sha256(value) and str(value).lower() != "0" * 64


def _without_hash(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != hash_field}


def _embedded_hash_valid(payload: Mapping[str, Any], hash_field: str) -> bool:
    actual = str(payload.get(hash_field, ""))
    return _is_sha256(actual) and actual == sha256_json(_without_hash(payload, hash_field))


def _walk_forbidden(obj: Any, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            lower = str(key).lower()
            if not isinstance(value, bool) and any(token in lower for token in FORBIDDEN_KEY_TOKENS):
                blockers.append(f"P68_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        lower = obj.lower()
        if any(token.lower() in lower for token in FORBIDDEN_VALUE_TOKENS):
            blockers.append(f"P68_FORBIDDEN_SECRET_OR_RAW_VALUE:{prefix or '<root>'}")
    return blockers


@dataclass(frozen=True)
class P68OperatorRunPackage:
    package_version: str = P68_VERSION
    artifact_type: str = "p68_real_order_test_operator_run_package"
    fixture_only: bool = False
    operator_request_id: str = "FILL_OPERATOR_REQUEST_ID"
    execution_scope: str = P68_TEMPLATE_SCOPE
    operator_phrase: str = EXACT_OPERATOR_PHRASE
    operator_confirmation_sha256: str = "0" * 64
    p65_report_sha256: str = "0" * 64
    p66_report_sha256: str = "0" * 64
    p67_report_sha256: str = "0" * 64
    p66_intake_path: str = "FILL_PATH_TO_ACCEPTED_P66_INTAKE_JSON"
    p66_validation_receipt_path: str = "FILL_PATH_TO_ACCEPTED_P66_VALIDATION_RECEIPT_JSON"
    p67_receipt_output_path: str = "FILL_PATH_TO_P67_REDACTED_RECEIPT_JSON"
    p67_validation_output_dir: str = "FILL_PATH_TO_P67_VALIDATION_OUTPUT_DIRECTORY"
    sender_program_reference: str = "operator-installed:binance-futures-testnet-order-test-sender"
    sender_program_sha256: str = "0" * 64
    launcher_reference: str = "operator-installed:fixed-launcher"
    launcher_sha256: str = "0" * 64
    credential_reference_id: str = "FILL_METADATA_ONLY_CREDENTIAL_REFERENCE"
    key_fingerprint_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_BASE_URL
    method: str = ALLOWED_METHOD
    path: str = ALLOWED_PATH
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    redacted_evidence_only: bool = True
    process_memory_credentials_only: bool = True
    shell_execution_allowed: bool = False
    parent_environment_inheritance_allowed: bool = False
    credential_argument_allowed: bool = False
    credential_stdin_allowed: bool = False
    real_order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    runtime_authority_granted: bool = False
    live_execution_allowed: bool = False
    auto_promotion_allowed: bool = False
    sender_execution_performed_by_p68: bool = False
    http_request_sent_by_p68: bool = False
    signature_created_by_p68: bool = False
    secret_value_accessed_by_p68: bool = False
    created_at_utc: str = "1970-01-01T00:00:00Z"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["operator_confirmation_sha256"] == "0" * 64:
            payload["operator_confirmation_sha256"] = sha256_text(self.operator_phrase)
        payload["p68_operator_run_package_sha256"] = sha256_json(payload)
        return payload


def validate_source_reports(
    p65_report: Mapping[str, Any] | None,
    p66_report: Mapping[str, Any] | None,
    p67_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    p65 = dict(p65_report or {})
    p66 = dict(p66_report or {})
    p67 = dict(p67_report or {})
    blockers = _walk_forbidden(p65) + _walk_forbidden(p66) + _walk_forbidden(p67)
    checks = (
        (p65, P65_SOURCE_STATUS, "p65_operator_installed_testnet_sender_executable_sha256", "P65"),
        (p66, P66_SOURCE_STATUS, "p66_operator_activation_intake_for_real_order_test_sha256", "P66"),
        (p67, P67_SOURCE_STATUS, "p67_real_order_test_redacted_evidence_receipt_report_sha256", "P67"),
    )
    for payload, expected_status, hash_field, label in checks:
        if payload.get("status") != expected_status:
            blockers.append(f"P68_{label}_SOURCE_STATUS_INVALID")
        if payload.get("review_only") is not True:
            blockers.append(f"P68_{label}_SOURCE_REVIEW_ONLY_REQUIRED")
        if not _embedded_hash_valid(payload, hash_field):
            blockers.append(f"P68_{label}_SOURCE_HASH_INVALID_OR_MISMATCH")
    if p65.get("no_network_sender_executable_self_test_passed") is not True:
        blockers.append("P68_P65_NO_NETWORK_SELF_TEST_NOT_PASSED")
    if p66.get("p66_operator_activation_intake_validator_implemented") is not True:
        blockers.append("P68_P66_VALIDATOR_NOT_IMPLEMENTED")
    if p67.get("p67_receipt_validator_implemented") is not True:
        blockers.append("P68_P67_VALIDATOR_NOT_IMPLEMENTED")
    if p67.get("p67_no_secret_scan_implemented") is not True:
        blockers.append("P68_P67_NO_SECRET_SCAN_NOT_IMPLEMENTED")
    for label, payload, keys in (
        ("P65", p65, ("external_sender_executable_enabled", "real_order_test_endpoint_call_performed", "actual_order_submission_performed", "secret_value_accessed", "runtime_mutation_performed")),
        ("P66", p66, ("real_order_test_activation_enabled", "real_order_test_endpoint_call_performed", "actual_order_submission_performed", "secret_value_accessed", "runtime_mutation_performed")),
        ("P67", p67, ("actual_redacted_order_test_receipt_received", "actual_order_submission_performed", "real_order_test_endpoint_call_performed_by_p67", "secret_value_accessed_by_p67", "runtime_mutation_performed")),
    ):
        for key in keys:
            if payload.get(key) is not False:
                blockers.append(f"P68_{label}_SOURCE_EXPECTED_FALSE:{key}")
    return {
        "source_reports_valid": not blockers,
        "source_report_block_reasons": sorted(dict.fromkeys(blockers)),
        "p65_report_sha256": p65.get("p65_operator_installed_testnet_sender_executable_sha256"),
        "p66_report_sha256": p66.get("p66_operator_activation_intake_for_real_order_test_sha256"),
        "p67_report_sha256": p67.get("p67_real_order_test_redacted_evidence_receipt_report_sha256"),
    }


def build_p68_operator_run_package_template(
    p65_report: Mapping[str, Any], p66_report: Mapping[str, Any], p67_report: Mapping[str, Any]
) -> dict[str, Any]:
    payload = P68OperatorRunPackage(
        p65_report_sha256=str(p65_report.get("p65_operator_installed_testnet_sender_executable_sha256", "0" * 64)),
        p66_report_sha256=str(p66_report.get("p66_operator_activation_intake_for_real_order_test_sha256", "0" * 64)),
        p67_report_sha256=str(p67_report.get("p67_real_order_test_redacted_evidence_receipt_report_sha256", "0" * 64)),
        created_at_utc=utc_now_canonical(),
    ).to_dict()
    return payload


def build_valid_p68_operator_run_package_fixture(
    p65_report: Mapping[str, Any], p66_report: Mapping[str, Any], p67_report: Mapping[str, Any]
) -> dict[str, Any]:
    return P68OperatorRunPackage(
        fixture_only=True,
        operator_request_id="p68-valid-operator-run-package-fixture",
        execution_scope=P68_ACTUAL_RUN_HANDOFF_SCOPE,
        p65_report_sha256=str(p65_report.get("p65_operator_installed_testnet_sender_executable_sha256")),
        p66_report_sha256=str(p66_report.get("p66_operator_activation_intake_for_real_order_test_sha256")),
        p67_report_sha256=str(p67_report.get("p67_real_order_test_redacted_evidence_receipt_report_sha256")),
        p66_intake_path="operator_inputs/p66_operator_activation_intake_ACCEPTED.json",
        p66_validation_receipt_path="operator_inputs/p66_activation_validation_receipt_ACCEPTED.json",
        p67_receipt_output_path="operator_outputs/p67_real_order_test_redacted_evidence_receipt.json",
        p67_validation_output_dir="operator_outputs/p67_validation",
        sender_program_reference="operator-installed:fixture-no-network-sender",
        sender_program_sha256="a" * 64,
        launcher_reference="operator-installed:fixture-launcher",
        launcher_sha256="b" * 64,
        credential_reference_id="metadata-only:operator-os-provider:binance-futures-testnet",
        key_fingerprint_sha256="c" * 64,
        one_shot_nonce_sha256="d" * 64,
        created_at_utc=utc_now_canonical(),
    ).to_dict()


def validate_p68_operator_run_package(
    package: Mapping[str, Any] | None,
    p65_report: Mapping[str, Any] | None,
    p66_report: Mapping[str, Any] | None,
    p67_report: Mapping[str, Any] | None,
    *,
    allow_fixture: bool = False,
) -> dict[str, Any]:
    payload = dict(package or {})
    blockers = _walk_forbidden(payload)
    sources = validate_source_reports(p65_report, p66_report, p67_report)
    blockers.extend(sources["source_report_block_reasons"])
    if not _embedded_hash_valid(payload, "p68_operator_run_package_sha256"):
        blockers.append("P68_RUN_PACKAGE_HASH_INVALID_OR_MISMATCH")
    fixture = payload.get("fixture_only") is True
    if fixture and not allow_fixture:
        blockers.append("P68_FIXTURE_RUN_PACKAGE_NOT_ALLOWED")
    if payload.get("execution_scope") != P68_ACTUAL_RUN_HANDOFF_SCOPE:
        blockers.append("P68_EXECUTION_SCOPE_INVALID")
    if payload.get("operator_phrase") != EXACT_OPERATOR_PHRASE:
        blockers.append("P68_OPERATOR_PHRASE_INVALID")
    if payload.get("operator_confirmation_sha256") != sha256_text(EXACT_OPERATOR_PHRASE):
        blockers.append("P68_OPERATOR_CONFIRMATION_HASH_INVALID")
    for key, expected in (
        ("p65_report_sha256", sources.get("p65_report_sha256")),
        ("p66_report_sha256", sources.get("p66_report_sha256")),
        ("p67_report_sha256", sources.get("p67_report_sha256")),
    ):
        if payload.get(key) != expected:
            blockers.append(f"P68_SOURCE_HASH_CHAIN_MISMATCH:{key}")
    for key in ("sender_program_sha256", "launcher_sha256", "key_fingerprint_sha256", "one_shot_nonce_sha256"):
        if not _is_nonzero_sha256(payload.get(key)):
            blockers.append(f"P68_NONZERO_SHA256_REQUIRED:{key}")
    if not str(payload.get("credential_reference_id", "")).startswith("metadata-only:"):
        blockers.append("P68_METADATA_ONLY_CREDENTIAL_REFERENCE_REQUIRED")
    for key in ("p66_intake_path", "p66_validation_receipt_path", "p67_receipt_output_path", "p67_validation_output_dir"):
        value = str(payload.get(key, "")).strip()
        if not value or value.startswith("FILL_"):
            blockers.append(f"P68_PATH_REQUIRED:{key}")
    for key, expected in (
        ("venue", ALLOWED_VENUE), ("base_url", ALLOWED_BASE_URL), ("method", ALLOWED_METHOD),
        ("path", ALLOWED_PATH), ("symbol", ALLOWED_SYMBOL),
    ):
        if payload.get(key) != expected:
            blockers.append(f"P68_SCOPE_INVALID:{key}")
    if payload.get("max_call_count") != 1:
        blockers.append("P68_MAX_CALL_COUNT_MUST_BE_ONE")
    for key in ("testnet_only", "order_test_only", "one_request_only", "redacted_evidence_only", "process_memory_credentials_only"):
        if payload.get(key) is not True:
            blockers.append(f"P68_EXPECTED_TRUE:{key}")
    for key in (
        "shell_execution_allowed", "parent_environment_inheritance_allowed", "credential_argument_allowed",
        "credential_stdin_allowed", "real_order_submit_allowed", "status_polling_allowed", "cancel_allowed",
        "runtime_authority_granted", "live_execution_allowed", "auto_promotion_allowed",
        "sender_execution_performed_by_p68", "http_request_sent_by_p68", "signature_created_by_p68",
        "secret_value_accessed_by_p68",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P68_EXPECTED_FALSE:{key}")
    valid = not blockers
    return {
        "status": STATUS_P68_VALIDATED if valid else STATUS_P68_BLOCKED,
        "p68_operator_run_package_valid": valid,
        "p68_operator_run_package_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": fixture,
        "eligible_for_operator_managed_external_order_test_run": valid and not fixture,
        "sender_execution_performed_by_p68": False,
        "http_request_sent_by_p68": False,
        "signature_created_by_p68": False,
        "secret_value_accessed_by_p68": False,
        "actual_order_submission_performed": False,
    }


def build_p68_preflight_checklist_template() -> dict[str, Any]:
    steps = [
        "verify_p65_p66_p67_source_hashes",
        "prepare_actual_nonfixture_p66_intake",
        "validate_p66_intake_and_receipt",
        "verify_operator_sender_installation_and_sha256",
        "verify_metadata_only_credential_reference_and_key_fingerprint",
        "verify_one_shot_nonce_freshness",
        "verify_system_clock_sync",
        "verify_testnet_base_url_and_order_test_path",
        "verify_output_directory_permissions",
        "run_external_sender_once_outside_crypto_ai_system",
        "capture_redacted_p67_receipt_only",
        "validate_p67_receipt_and_no_secret_scan",
    ]
    payload = {
        "artifact_type": "p68_real_order_test_operator_preflight_checklist",
        "review_only": True,
        "execution_performed": False,
        "required_step_order": steps,
        "operator_checkboxes": {step: False for step in steps},
        "all_preflight_checks_completed": False,
        "actual_order_submission_performed": False,
    }
    payload["p68_preflight_checklist_sha256"] = sha256_json(payload)
    return payload


def build_p68_invocation_manifest_template() -> dict[str, Any]:
    payload = {
        "artifact_type": "p68_external_sender_invocation_manifest",
        "review_only": True,
        "execution_performed": False,
        "launcher_path": "FILL_ABSOLUTE_LAUNCHER_PATH",
        "launcher_sha256": "0" * 64,
        "sender_program_path": "FILL_ABSOLUTE_SENDER_PROGRAM_PATH",
        "sender_program_sha256": "0" * 64,
        "metadata_request_path": "FILL_PATH_TO_METADATA_ONLY_REQUEST_JSON",
        "redacted_receipt_output_path": "FILL_PATH_TO_P67_REDACTED_RECEIPT_JSON",
        "shell": False,
        "inherit_parent_environment": False,
        "stdin_enabled": False,
        "credential_argument_allowed": False,
        "credential_stdin_allowed": False,
        "secret_file_path_allowed": False,
        "testnet_only": True,
        "order_test_only": True,
        "max_call_count": 1,
        "real_order_submit_allowed": False,
        "runtime_authority_granted": False,
    }
    payload["p68_invocation_manifest_sha256"] = sha256_json(payload)
    return payload


def build_p68_evidence_capture_manifest_template() -> dict[str, Any]:
    payload = {
        "artifact_type": "p68_redacted_evidence_capture_manifest",
        "review_only": True,
        "expected_receipt_type": "p67_real_order_test_redacted_evidence_receipt",
        "expected_outputs": [
            "p67_real_order_test_redacted_evidence_receipt.json",
            "p67_real_order_test_redacted_evidence_validation.json",
            "p67_real_order_test_no_secret_scan.json",
            "p67_order_test_dry_validation_bridge.json",
        ],
        "required_validation_script": "scripts/validate_p67_real_order_test_redacted_evidence_receipt.py",
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "real_signed_testnet_submit_evidence_present": False,
        "actual_order_submission_performed": False,
    }
    payload["p68_evidence_capture_manifest_sha256"] = sha256_json(payload)
    return payload


def build_p68_negative_fixture_results(
    p65_report: Mapping[str, Any], p66_report: Mapping[str, Any], p67_report: Mapping[str, Any]
) -> dict[str, Any]:
    base = build_valid_p68_operator_run_package_fixture(p65_report, p66_report, p67_report)
    cases: list[tuple[str, dict[str, Any]]] = []
    def add(name: str, **updates: Any) -> None:
        item = dict(base); item.update(updates); item.pop("p68_operator_run_package_sha256", None); item["p68_operator_run_package_sha256"] = sha256_json(item); cases.append((name, item))
    add("mainnet_url", base_url="https://fapi.binance.com")
    add("real_submit_path", path="/fapi/v1/order")
    add("wrong_symbol", symbol="ETHUSDT")
    add("shell_execution", shell_execution_allowed=True)
    add("parent_environment_inheritance", parent_environment_inheritance_allowed=True)
    add("credential_argument", credential_argument_allowed=True)
    add("runtime_authority", runtime_authority_granted=True)
    add("real_order_submit", real_order_submit_allowed=True)
    add("missing_sender_hash", sender_program_sha256="0" * 64)
    add("bad_operator_phrase", operator_phrase="APPROVE EVERYTHING")
    secret = dict(base); secret["api_secret_value"] = "forbidden"; secret.pop("p68_operator_run_package_sha256", None); secret["p68_operator_run_package_sha256"] = sha256_json(secret); cases.append(("raw_secret_field", secret))
    add("source_hash_mismatch", p67_report_sha256="1" * 64)
    results = []
    for name, item in cases:
        validation = validate_p68_operator_run_package(item, p65_report, p66_report, p67_report, allow_fixture=True)
        results.append({"case": name, "blocked": validation["p68_operator_run_package_valid"] is False, "block_reasons": validation["p68_operator_run_package_block_reasons"]})
    payload = {"artifact_type": "p68_real_order_test_operator_run_package_negative_fixture_results", "case_count": len(results), "all_negative_fixtures_blocked": all(x["blocked"] for x in results), "results": results}
    payload["p68_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_p68_real_order_test_operator_run_package_report(
    p65_report: Mapping[str, Any], p66_report: Mapping[str, Any], p67_report: Mapping[str, Any]
) -> dict[str, Any]:
    sources = validate_source_reports(p65_report, p66_report, p67_report)
    template = build_p68_operator_run_package_template(p65_report, p66_report, p67_report)
    fixture = build_valid_p68_operator_run_package_fixture(p65_report, p66_report, p67_report)
    fixture_validation = validate_p68_operator_run_package(fixture, p65_report, p66_report, p67_report, allow_fixture=True)
    checklist = build_p68_preflight_checklist_template()
    invocation = build_p68_invocation_manifest_template()
    capture = build_p68_evidence_capture_manifest_template()
    negatives = build_p68_negative_fixture_results(p65_report, p66_report, p67_report)
    ready = sources["source_reports_valid"] and fixture_validation["p68_operator_run_package_valid"] and negatives["all_negative_fixtures_blocked"]
    report = {
        "artifact_type": "p68_real_order_test_operator_run_package_report",
        "status": STATUS_P68_READY if ready else STATUS_P68_BLOCKED,
        "blocked": not ready,
        "review_only": True,
        "runtime_authority_source": False,
        "p68_operator_run_package_validator_implemented": True,
        "p68_operator_preflight_checklist_implemented": True,
        "p68_invocation_manifest_implemented": True,
        "p68_redacted_evidence_capture_manifest_implemented": True,
        "source_validation": sources,
        "operator_run_package_template": template,
        "valid_fixture_operator_run_package": fixture,
        "valid_fixture_validation": fixture_validation,
        "preflight_checklist_template": checklist,
        "invocation_manifest_template": invocation,
        "evidence_capture_manifest_template": capture,
        "negative_fixture_summary": {"case_count": negatives["case_count"], "all_blocked": negatives["all_negative_fixtures_blocked"]},
        "negative_fixtures_all_blocked": negatives["all_negative_fixtures_blocked"],
        "actual_operator_run_package_received": False,
        "actual_operator_run_package_accepted": False,
        "eligible_for_operator_managed_external_order_test_run": False,
        "sender_execution_performed_by_p68": False,
        "real_order_test_endpoint_call_performed_by_p68": False,
        "http_request_sent_by_p68": False,
        "signature_created_by_p68": False,
        "signed_request_created_by_p68": False,
        "secret_value_accessed_by_p68": False,
        "secret_value_logged_by_p68": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "actual_live_order_submitted": False,
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "runtime_mutation_performed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["p68_real_order_test_operator_run_package_report_sha256"] = sha256_json(report)
    return report


def _markdown_report(report: Mapping[str, Any]) -> str:
    return f"""# P68 Real `/order/test` Operator Run Package Report

## Status

`{report.get('status')}`

## Purpose

P68 packages the final operator handoff needed to perform one externally managed Binance Futures testnet `POST /fapi/v1/order/test` validation and return only a redacted P67 receipt. P68 never reads credentials, launches the sender, signs, sends HTTP, or submits an order.

## Required operator sequence

1. Create a real, non-fixture P66 intake and validate it.
2. Verify the operator-installed sender and launcher SHA256 values.
3. Confirm metadata-only credential reference, key fingerprint, one-shot nonce, and clock sync.
4. Run the external sender exactly once outside Crypto_AI_System.
5. Save only the redacted P67 receipt.
6. Run the P67 validator and no-secret scan.
7. Do not feed `/order/test` evidence to P50 or P7.

## Current truth

- actual operator run package received: `{str(report.get('actual_operator_run_package_received')).lower()}`
- eligible for external order-test run: `{str(report.get('eligible_for_operator_managed_external_order_test_run')).lower()}`
- sender execution performed by P68: `{str(report.get('sender_execution_performed_by_p68')).lower()}`
- actual order submission performed: `{str(report.get('actual_order_submission_performed')).lower()}`

## Safety

All credential access, signing, HTTP, order submission, runtime mutation, and live execution flags remain false.
"""


def build_p68_operator_runbook_markdown() -> str:
    return """# P68 Operator Runbook — One Real Binance Futures Testnet `/order/test`

## Boundary

This runbook prepares one external `/fapi/v1/order/test` validation. It does not submit an order and it must never call `/fapi/v1/order`.

## Before execution

1. Keep API key and API secret values outside Crypto_AI_System, chat, ZIPs, JSON artifacts, logs, and screenshots.
2. Prepare a real non-fixture P66 intake using the exact operator phrase.
3. Validate the P66 intake and retain the accepted validation receipt.
4. Verify the installed sender executable and launcher by absolute path and SHA256.
5. Verify the testnet-only scope: `https://demo-fapi.binance.com`, `POST /fapi/v1/order/test`, `BTCUSDT`, one request.
6. Verify local clock synchronization and a fresh one-shot nonce.
7. Confirm the output directory contains no previous receipt with the same nonce.

## External execution

The sender must be launched outside Crypto_AI_System. No credential value may be passed through CLI arguments, stdin, JSON, logs, or the parent process. The sender may use credentials only inside its own process-memory boundary and must output one redacted JSON receipt.

## After execution

1. Save the redacted receipt to the P67 receipt path.
2. Validate it with `scripts/validate_p67_real_order_test_redacted_evidence_receipt.py`.
3. Confirm the no-secret scan passes.
4. Confirm `order_created=false`, `actual_order_submission_performed=false`, and both P50/P7 eligibility flags remain false.
5. Archive only the redacted receipt, validation, no-secret scan, and bridge result.

## Stop conditions

Stop immediately on any mainnet URL, `/fapi/v1/order` path, unexpected symbol, duplicate nonce, executable hash mismatch, non-empty raw response persistence, credential exposure, HTTP ambiguity, or missing redaction evidence.
"""


def persist_p68_real_order_test_operator_run_package(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    p65 = read_json(latest / "p65_operator_installed_testnet_sender_executable_report.json", {})
    p66 = read_json(latest / "p66_operator_activation_intake_for_real_order_test_report.json", {})
    p67 = read_json(latest / "p67_real_order_test_redacted_evidence_receipt_report.json", {})
    report = build_p68_real_order_test_operator_run_package_report(p65, p66, p67)
    negatives = build_p68_negative_fixture_results(p65, p66, p67)
    outputs = {
        "p68_real_order_test_operator_run_package_report.json": report,
        "p68_real_order_test_operator_run_package_TEMPLATE_REVIEW_ONLY_NO_CALL.json": report["operator_run_package_template"],
        "p68_real_order_test_operator_run_package_VALID_FIXTURE_ONLY.json": report["valid_fixture_operator_run_package"],
        "p68_real_order_test_operator_run_package_validation_FIXTURE_ONLY.json": report["valid_fixture_validation"],
        "p68_real_order_test_operator_preflight_checklist_TEMPLATE.json": report["preflight_checklist_template"],
        "p68_external_sender_invocation_manifest_TEMPLATE_NO_EXECUTION.json": report["invocation_manifest_template"],
        "p68_redacted_evidence_capture_manifest_TEMPLATE.json": report["evidence_capture_manifest_template"],
        "p68_real_order_test_operator_run_package_negative_fixture_results.json": negatives,
        "p68_real_order_test_operator_run_package_summary.json": {
            "status": report["status"], "review_only": True,
            "actual_operator_run_package_received": False,
            "eligible_for_operator_managed_external_order_test_run": False,
            "sender_execution_performed_by_p68": False,
            "actual_order_submission_performed": False,
        },
    }
    phase_dir = root / "storage" / "p68_real_order_test_operator_run_package"
    for name, payload in outputs.items():
        atomic_write_json(latest / name, payload); atomic_write_json(phase_dir / name, payload)
    row = {
        "registry_name": P68_REGISTRY_NAME, "status": report["status"],
        "report_sha256": report["p68_real_order_test_operator_run_package_report_sha256"],
        "review_only": True, "actual_operator_run_package_received": False,
        "sender_execution_performed": False, "actual_order_submission_performed": False,
        "created_at_utc": report["created_at_utc"],
    }
    row["registry_record_sha256"] = sha256_json(row)
    append_jsonl(root / "storage" / "registries" / f"{P68_REGISTRY_NAME}.jsonl", row)
    atomic_write_json(latest / "p68_real_order_test_operator_run_package_registry_record.json", row)
    atomic_write_json(phase_dir / "p68_real_order_test_operator_run_package_registry_record.json", row)
    (root / "P68_REAL_ORDER_TEST_OPERATOR_RUN_PACKAGE_REPORT.md").write_text(_markdown_report(report), encoding="utf-8")
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "P68_REAL_ORDER_TEST_OPERATOR_RUNBOOK.md").write_text(build_p68_operator_runbook_markdown(), encoding="utf-8")
    return report


__all__ = [
    "P68_VERSION", "STATUS_P68_READY", "STATUS_P68_VALIDATED", "STATUS_P68_BLOCKED",
    "P68OperatorRunPackage", "validate_source_reports", "build_p68_operator_run_package_template",
    "build_valid_p68_operator_run_package_fixture", "validate_p68_operator_run_package",
    "build_p68_preflight_checklist_template", "build_p68_invocation_manifest_template",
    "build_p68_evidence_capture_manifest_template", "build_p68_negative_fixture_results",
    "build_p68_real_order_test_operator_run_package_report", "persist_p68_real_order_test_operator_run_package",
]
