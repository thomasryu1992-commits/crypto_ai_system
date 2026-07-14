from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_ai_system.execution.real_order_test_redacted_evidence_receipt import (
    FIXTURE_EVIDENCE_ORIGIN,
    REAL_EVIDENCE_ORIGIN,
    STATUS_P67_ACCEPTED,
    STATUS_P67_READY,
    atomic_write_json,
    build_p67_negative_fixture_results,
    build_p67_no_secret_scan_report,
    build_p67_order_test_validation_bridge,
    build_p67_real_order_test_redacted_evidence_receipt_report,
    build_valid_p67_receipt_fixture,
    persist_p67_real_order_test_redacted_evidence_receipt,
    validate_p66_activation_chain,
    validate_p66_source_report,
    validate_p67_receipt_files,
    validate_p67_redacted_evidence_receipt,
)
from crypto_ai_system.execution.operator_activation_intake_for_real_order_test import (
    build_p66_operator_activation_intake_report,
)
from crypto_ai_system.utils.audit import sha256_json
from external_runtime_packages.binance_futures_testnet_adapter import (
    build_p65_operator_installed_sender_executable_report,
)

NOW = datetime(2026, 7, 12, 5, 0, 0, tzinfo=timezone.utc)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _p66_report() -> dict:
    return build_p66_operator_activation_intake_report(
        build_p65_operator_installed_sender_executable_report(), now=NOW
    )


def _fixture_chain(report: dict) -> tuple[dict, dict]:
    template = dict(report["operator_activation_intake_template"])
    template.update(
        {
            "operator_request_id": "p67-valid-operator-fixture",
            "approval_granted": True,
            "actual_operator_supplied": True,
            "fixture_only": True,
            "execution_scope": "p65_approved_testnet_order_test_only",
            "credential_reference_id": "metadata-only:operator-os-provider:binance-futures-testnet",
            "key_fingerprint_sha256": "c" * 64,
            "one_shot_nonce_sha256": "d" * 64,
        }
    )
    template.pop("p66_operator_activation_intake_sha256", None)
    template["p66_operator_activation_intake_sha256"] = sha256_json(template)
    receipt = dict(report["approved_fixture_receipt"])
    receipt.update(
        {
            "operator_request_id": template["operator_request_id"],
            "operator_activation_intake_sha256": template["p66_operator_activation_intake_sha256"],
            "key_fingerprint_sha256": template["key_fingerprint_sha256"],
            "one_shot_nonce_sha256": template["one_shot_nonce_sha256"],
            "fixture_validation_only": True,
        }
    )
    receipt.pop("p66_activation_validation_receipt_sha256", None)
    receipt["p66_activation_validation_receipt_sha256"] = sha256_json(receipt)
    return template, receipt


def _actual_chain(report: dict) -> tuple[dict, dict]:
    intake, receipt = _fixture_chain(report)
    intake = dict(intake)
    intake["fixture_only"] = False
    intake["operator_request_id"] = "actual-operator-request-001"
    intake.pop("p66_operator_activation_intake_sha256", None)
    intake["p66_operator_activation_intake_sha256"] = sha256_json(intake)
    receipt = dict(receipt)
    receipt["fixture_validation_only"] = False
    receipt["operator_request_id"] = intake["operator_request_id"]
    receipt["operator_activation_intake_sha256"] = intake["p66_operator_activation_intake_sha256"]
    receipt.pop("p66_activation_validation_receipt_sha256", None)
    receipt["p66_activation_validation_receipt_sha256"] = sha256_json(receipt)
    return intake, receipt


def _actual_receipt(intake: dict, p66_receipt: dict) -> dict:
    payload = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    payload.update(
        {
            "evidence_origin": REAL_EVIDENCE_ORIGIN,
            "fixture_only": False,
            "actual_external_runtime_execution": True,
        }
    )
    payload.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    payload["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(payload)
    return payload


def test_p67_p66_source_valid():
    result = validate_p66_source_report(_p66_report())
    assert result["p66_source_valid"] is True
    assert result["p66_source_block_reasons"] == []


def test_p67_fixture_activation_chain_valid_only_when_allowed():
    intake, receipt = _fixture_chain(_p66_report())
    allowed = validate_p66_activation_chain(intake, receipt, allow_fixture=True)
    blocked = validate_p66_activation_chain(intake, receipt, allow_fixture=False)
    assert allowed["p66_activation_chain_valid"] is True
    assert blocked["p66_activation_chain_valid"] is False


def test_p67_fixture_receipt_valid_for_fixture_only():
    intake, p66_receipt = _fixture_chain(_p66_report())
    receipt = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    result = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=True, now=NOW + timedelta(seconds=2)
    )
    assert result["status"] == STATUS_P67_ACCEPTED
    assert result["p67_redacted_evidence_receipt_valid"] is True
    assert result["actual_real_order_test_evidence_accepted"] is False
    assert result["p50_external_evidence_import_eligible"] is False
    assert result["p7_post_submit_evidence_import_eligible"] is False


def test_p67_actual_receipt_accepted_as_order_test_only():
    intake, p66_receipt = _actual_chain(_p66_report())
    receipt = _actual_receipt(intake, p66_receipt)
    result = validate_p67_redacted_evidence_receipt(receipt, intake, p66_receipt, now=NOW + timedelta(seconds=2))
    assert result["p67_redacted_evidence_receipt_valid"] is True
    assert result["actual_real_order_test_evidence_accepted"] is True
    assert result["order_test_dry_validation_proven"] is True
    assert result["eligible_for_next_signed_testnet_submit_preflight"] is True
    assert result["p50_external_evidence_import_eligible"] is False
    assert result["p7_post_submit_evidence_import_eligible"] is False


def test_p67_actual_receipt_requires_actual_execution_claim():
    intake, p66_receipt = _actual_chain(_p66_report())
    receipt = _actual_receipt(intake, p66_receipt)
    receipt["actual_external_runtime_execution"] = False
    receipt.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    receipt["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(receipt)
    result = validate_p67_redacted_evidence_receipt(receipt, intake, p66_receipt, now=NOW + timedelta(seconds=2))
    assert "P67_ACTUAL_EXTERNAL_RUNTIME_EXECUTION_REQUIRED" in result["p67_redacted_evidence_receipt_block_reasons"]


def test_p67_blocks_mainnet_submit_order_created_and_raw_response():
    intake, p66_receipt = _fixture_chain(_p66_report())
    receipt = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    receipt.update(
        {
            "base_url": "https://fapi.binance.com",
            "path": "/fapi/v1/order",
            "order_created": True,
            "raw_response_persisted": True,
        }
    )
    receipt.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    receipt["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(receipt)
    result = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=True, now=NOW + timedelta(seconds=2)
    )
    reasons = result["p67_redacted_evidence_receipt_block_reasons"]
    assert "P67_RECEIPT_SCOPE_INVALID:base_url" in reasons
    assert "P67_RECEIPT_SCOPE_INVALID:path" in reasons
    assert "P67_EXPECTED_FALSE:order_created" in reasons
    assert "P67_EXPECTED_FALSE:raw_response_persisted" in reasons


def test_p67_blocks_secret_field_and_hash_mismatch():
    intake, p66_receipt = _fixture_chain(_p66_report())
    receipt = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    receipt["api_secret_value"] = "forbidden"
    result = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=True, now=NOW + timedelta(seconds=2)
    )
    assert any("P67_FORBIDDEN_SECRET_OR_RAW_FIELD" in item for item in result["p67_redacted_evidence_receipt_block_reasons"])
    assert "P67_RECEIPT_HASH_INVALID_OR_MISMATCH" in result["p67_redacted_evidence_receipt_block_reasons"]


def test_p67_blocks_nonce_mismatch_and_delayed_receipt():
    intake, p66_receipt = _fixture_chain(_p66_report())
    receipt = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    receipt["one_shot_nonce_sha256"] = "1" * 64
    receipt["received_at_utc"] = "2026-07-12T05:15:01Z"
    receipt.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    receipt["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(receipt)
    result = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=True, now=NOW + timedelta(minutes=16)
    )
    assert "P67_NONCE_MISMATCH" in result["p67_redacted_evidence_receipt_block_reasons"]
    assert "P67_RECEIPT_DELAY_EXCEEDED" in result["p67_redacted_evidence_receipt_block_reasons"]


def test_p67_no_secret_scan_and_bridge_keep_p50_p7_blocked():
    intake, p66_receipt = _fixture_chain(_p66_report())
    receipt = build_valid_p67_receipt_fixture(intake, p66_receipt, now=NOW)
    validation = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=True, now=NOW + timedelta(seconds=2)
    )
    scan = build_p67_no_secret_scan_report(receipt)
    bridge = build_p67_order_test_validation_bridge(receipt, validation, fixture_validation_only=True)
    assert scan["scan_passed"] is True
    assert bridge["p50_external_evidence_import_eligible"] is False
    assert bridge["p7_post_submit_evidence_import_eligible"] is False
    assert bridge["order_created"] is False


def test_p67_negative_fixtures_all_blocked():
    result = build_p67_negative_fixture_results(_p66_report(), now=NOW)
    assert result["case_count"] == 12
    assert result["all_negative_fixtures_blocked"] is True


def test_p67_report_ready_and_does_not_claim_real_evidence():
    report = build_p67_real_order_test_redacted_evidence_receipt_report(_p66_report(), now=NOW)
    assert report["status"] == STATUS_P67_READY
    assert report["actual_redacted_order_test_receipt_received"] is False
    assert report["actual_real_order_test_dry_validation_proven"] is False
    assert report["p50_external_evidence_import_eligible"] is False
    assert report["p7_post_submit_evidence_import_eligible"] is False
    assert report["actual_order_submission_performed"] is False


def test_p67_file_validation_actual_receipt(tmp_path: Path):
    intake, p66_receipt = _actual_chain(_p66_report())
    receipt = _actual_receipt(intake, p66_receipt)
    receipt_path = tmp_path / "receipt.json"
    intake_path = tmp_path / "intake.json"
    p66_receipt_path = tmp_path / "p66_receipt.json"
    atomic_write_json(receipt_path, receipt)
    atomic_write_json(intake_path, intake)
    atomic_write_json(p66_receipt_path, p66_receipt)
    validation, scan, bridge = validate_p67_receipt_files(
        receipt_path, intake_path, p66_receipt_path, now=NOW + timedelta(seconds=2)
    )
    assert validation["actual_real_order_test_evidence_accepted"] is True
    assert scan["scan_passed"] is True
    assert bridge["eligible_for_next_signed_testnet_submit_preflight"] is True
    assert bridge["p50_external_evidence_import_eligible"] is False


def test_p67_persist_outputs(tmp_path: Path):
    latest = tmp_path / "storage/latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "p66_operator_activation_intake_for_real_order_test_report.json", _p66_report())
    report = persist_p67_real_order_test_redacted_evidence_receipt(tmp_path)
    assert report["status"] == STATUS_P67_READY
    assert (latest / "p67_real_order_test_redacted_evidence_receipt_report.json").exists()
    assert (latest / "p67_real_order_test_redacted_evidence_receipt_TEMPLATE_REVIEW_ONLY_NO_SUBMIT.json").exists()
    assert (tmp_path / "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_REPORT.md").exists()
