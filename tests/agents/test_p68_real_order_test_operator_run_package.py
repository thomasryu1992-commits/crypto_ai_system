from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.execution.real_order_test_operator_run_package import (
    ALLOWED_BASE_URL,
    P68_ACTUAL_RUN_HANDOFF_SCOPE,
    STATUS_P68_READY,
    STATUS_P68_VALIDATED,
    atomic_write_json,
    build_p68_evidence_capture_manifest_template,
    build_p68_invocation_manifest_template,
    build_p68_negative_fixture_results,
    build_p68_preflight_checklist_template,
    build_p68_real_order_test_operator_run_package_report,
    build_valid_p68_operator_run_package_fixture,
    persist_p68_real_order_test_operator_run_package,
    validate_p68_operator_run_package,
    validate_source_reports,
)
from crypto_ai_system.execution.operator_activation_intake_for_real_order_test import (
    build_p66_operator_activation_intake_report,
)
from crypto_ai_system.execution.real_order_test_redacted_evidence_receipt import (
    build_p67_real_order_test_redacted_evidence_receipt_report,
)
from crypto_ai_system.utils.audit import sha256_json
from external_runtime_packages.binance_futures_testnet_adapter import (
    build_p65_operator_installed_sender_executable_report,
)


def _latest() -> Path:
    return Path(__file__).resolve().parents[2] / "storage" / "latest"


def _load(name: str) -> dict:
    return json.loads((_latest() / name).read_text(encoding="utf-8"))


def _sources() -> tuple[dict, dict, dict]:
    p65 = build_p65_operator_installed_sender_executable_report()
    p66 = build_p66_operator_activation_intake_report(p65)
    p67 = build_p67_real_order_test_redacted_evidence_receipt_report(p66)
    return p65, p66, p67


def _actual_package() -> tuple[dict, dict, dict, dict]:
    p65, p66, p67 = _sources()
    package = build_valid_p68_operator_run_package_fixture(p65, p66, p67)
    package["fixture_only"] = False
    package["operator_request_id"] = "actual-operator-run-package-001"
    package["sender_program_reference"] = "operator-installed:validated-testnet-order-test-sender"
    package["launcher_reference"] = "operator-installed:validated-fixed-launcher"
    package.pop("p68_operator_run_package_sha256", None)
    package["p68_operator_run_package_sha256"] = sha256_json(package)
    return package, p65, p66, p67


def test_p68_source_reports_valid():
    p65, p66, p67 = _sources()
    result = validate_source_reports(p65, p66, p67)
    assert result["source_reports_valid"] is True
    assert result["source_report_block_reasons"] == []


def test_p68_fixture_package_valid_only_when_allowed():
    p65, p66, p67 = _sources()
    package = build_valid_p68_operator_run_package_fixture(p65, p66, p67)
    allowed = validate_p68_operator_run_package(package, p65, p66, p67, allow_fixture=True)
    blocked = validate_p68_operator_run_package(package, p65, p66, p67, allow_fixture=False)
    assert allowed["status"] == STATUS_P68_VALIDATED
    assert allowed["p68_operator_run_package_valid"] is True
    assert allowed["eligible_for_operator_managed_external_order_test_run"] is False
    assert blocked["p68_operator_run_package_valid"] is False


def test_p68_actual_handoff_package_can_be_eligible_without_execution():
    package, p65, p66, p67 = _actual_package()
    result = validate_p68_operator_run_package(package, p65, p66, p67)
    assert result["p68_operator_run_package_valid"] is True
    assert result["eligible_for_operator_managed_external_order_test_run"] is True
    assert result["sender_execution_performed_by_p68"] is False
    assert result["actual_order_submission_performed"] is False


def test_p68_blocks_mainnet_and_real_submit_path():
    package, p65, p66, p67 = _actual_package()
    package.update({"base_url": "https://fapi.binance.com", "path": "/fapi/v1/order"})
    package.pop("p68_operator_run_package_sha256", None)
    package["p68_operator_run_package_sha256"] = sha256_json(package)
    result = validate_p68_operator_run_package(package, p65, p66, p67)
    assert "P68_SCOPE_INVALID:base_url" in result["p68_operator_run_package_block_reasons"]
    assert "P68_SCOPE_INVALID:path" in result["p68_operator_run_package_block_reasons"]


def test_p68_blocks_shell_parent_env_and_credential_args():
    package, p65, p66, p67 = _actual_package()
    package.update({"shell_execution_allowed": True, "parent_environment_inheritance_allowed": True, "credential_argument_allowed": True})
    package.pop("p68_operator_run_package_sha256", None)
    package["p68_operator_run_package_sha256"] = sha256_json(package)
    result = validate_p68_operator_run_package(package, p65, p66, p67)
    reasons = result["p68_operator_run_package_block_reasons"]
    assert "P68_EXPECTED_FALSE:shell_execution_allowed" in reasons
    assert "P68_EXPECTED_FALSE:parent_environment_inheritance_allowed" in reasons
    assert "P68_EXPECTED_FALSE:credential_argument_allowed" in reasons


def test_p68_blocks_secret_field_and_bad_hash():
    package, p65, p66, p67 = _actual_package()
    package["api_secret_value"] = "forbidden"
    result = validate_p68_operator_run_package(package, p65, p66, p67)
    assert any("P68_FORBIDDEN_SECRET_OR_RAW_FIELD" in x for x in result["p68_operator_run_package_block_reasons"])
    assert "P68_RUN_PACKAGE_HASH_INVALID_OR_MISMATCH" in result["p68_operator_run_package_block_reasons"]


def test_p68_preflight_checklist_has_fixed_safe_order():
    checklist = build_p68_preflight_checklist_template()
    assert checklist["execution_performed"] is False
    assert checklist["required_step_order"][0] == "verify_p65_p66_p67_source_hashes"
    assert checklist["required_step_order"][-1] == "validate_p67_receipt_and_no_secret_scan"
    assert checklist["all_preflight_checks_completed"] is False


def test_p68_invocation_manifest_never_carries_credentials():
    manifest = build_p68_invocation_manifest_template()
    assert manifest["shell"] is False
    assert manifest["inherit_parent_environment"] is False
    assert manifest["credential_argument_allowed"] is False
    assert manifest["credential_stdin_allowed"] is False
    assert manifest["real_order_submit_allowed"] is False
    assert manifest["base_url"] if "base_url" in manifest else ALLOWED_BASE_URL


def test_p68_capture_manifest_keeps_p50_p7_blocked():
    manifest = build_p68_evidence_capture_manifest_template()
    assert manifest["expected_receipt_type"] == "p67_real_order_test_redacted_evidence_receipt"
    assert manifest["p50_external_evidence_import_eligible"] is False
    assert manifest["p7_post_submit_evidence_import_eligible"] is False
    assert manifest["actual_order_submission_performed"] is False


def test_p68_negative_fixtures_all_blocked():
    p65, p66, p67 = _sources()
    result = build_p68_negative_fixture_results(p65, p66, p67)
    assert result["case_count"] == 12
    assert result["all_negative_fixtures_blocked"] is True


def test_p68_report_ready_and_does_not_claim_execution():
    p65, p66, p67 = _sources()
    report = build_p68_real_order_test_operator_run_package_report(p65, p66, p67)
    assert report["status"] == STATUS_P68_READY
    assert report["actual_operator_run_package_received"] is False
    assert report["eligible_for_operator_managed_external_order_test_run"] is False
    assert report["sender_execution_performed_by_p68"] is False
    assert report["actual_order_submission_performed"] is False


def test_p68_source_hash_mismatch_blocks():
    package, p65, p66, p67 = _actual_package()
    package["p67_report_sha256"] = "1" * 64
    package.pop("p68_operator_run_package_sha256", None)
    package["p68_operator_run_package_sha256"] = sha256_json(package)
    result = validate_p68_operator_run_package(package, p65, p66, p67)
    assert "P68_SOURCE_HASH_CHAIN_MISMATCH:p67_report_sha256" in result["p68_operator_run_package_block_reasons"]


def test_p68_persist_outputs(tmp_path: Path):
    latest = tmp_path / "storage/latest"
    latest.mkdir(parents=True)
    p65, p66, p67 = _sources()
    atomic_write_json(latest / "p65_operator_installed_testnet_sender_executable_report.json", p65)
    atomic_write_json(latest / "p66_operator_activation_intake_for_real_order_test_report.json", p66)
    atomic_write_json(latest / "p67_real_order_test_redacted_evidence_receipt_report.json", p67)
    report = persist_p68_real_order_test_operator_run_package(tmp_path)
    assert report["status"] == STATUS_P68_READY
    assert (latest / "p68_real_order_test_operator_run_package_report.json").exists()
    assert (latest / "p68_real_order_test_operator_preflight_checklist_TEMPLATE.json").exists()
    assert (tmp_path / "P68_REAL_ORDER_TEST_OPERATOR_RUN_PACKAGE_REPORT.md").exists()
    assert (tmp_path / "docs/P68_REAL_ORDER_TEST_OPERATOR_RUNBOOK.md").exists()
