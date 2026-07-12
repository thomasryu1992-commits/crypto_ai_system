from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.execution.operator_activation_intake_for_real_order_test import (
    ALLOWED_PATH,
    P65_APPROVED_ORDER_TEST_SCOPE,
    STATUS_P66_ACCEPTED,
    STATUS_P66_READY,
    build_p66_activation_validation_receipt,
    build_p66_negative_fixture_results,
    build_p66_operator_activation_intake_report,
    build_p66_operator_activation_intake_template,
    build_valid_p66_operator_activation_intake_fixture,
    persist_p66_operator_activation_intake_for_real_order_test,
    validate_p65_source_report,
    validate_p66_intake_file,
    validate_p66_operator_activation_intake,
)
from crypto_ai_system.utils.audit import sha256_json
from external_runtime_packages.binance_futures_testnet_adapter import (
    build_p65_operator_installed_sender_executable_report,
)

NOW = datetime(2026, 7, 12, 4, 0, 0, tzinfo=timezone.utc)


def _source() -> dict:
    return build_p65_operator_installed_sender_executable_report()


def _actual_from_fixture(payload: dict, **updates) -> dict:
    result = dict(payload)
    result.pop("p66_operator_activation_intake_sha256", None)
    result["fixture_only"] = False
    result.update(updates)
    result["p66_operator_activation_intake_sha256"] = sha256_json(result)
    return result


def test_p66_p65_source_report_valid():
    result = validate_p65_source_report(_source())
    assert result["p65_source_valid"] is True
    assert result["p65_source_block_reasons"] == []


def test_p66_template_valid_and_not_approved():
    source = _source()
    template = build_p66_operator_activation_intake_template(source, now=NOW)
    result = validate_p66_operator_activation_intake(template, source, require_approved=False, now=NOW)
    assert result["status"] == STATUS_P66_READY
    assert result["p66_operator_activation_intake_valid"] is True
    assert template["approval_granted"] is False
    assert template["real_order_submit_allowed"] is False


def test_p66_approved_fixture_valid_for_fixture_validation_only():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    result = validate_p66_operator_activation_intake(
        fixture, source, require_approved=True, allow_fixture=True, now=NOW
    )
    assert result["status"] == STATUS_P66_ACCEPTED
    assert result["operator_activation_intake_accepted"] is True
    assert result["real_order_test_execution_enabled"] is False


def test_p66_actual_validation_rejects_fixture():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    result = validate_p66_operator_activation_intake(
        fixture, source, require_approved=True, allow_fixture=False, now=NOW
    )
    assert result["p66_operator_activation_intake_valid"] is False
    assert "P66_FIXTURE_NOT_ALLOWED_FOR_ACTUAL_INTAKE" in result["p66_operator_activation_intake_block_reasons"]


def test_p66_actual_nonfixture_intake_can_be_accepted_without_execution():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    actual = _actual_from_fixture(fixture, operator_request_id="operator-request-001")
    result = validate_p66_operator_activation_intake(
        actual, source, require_approved=True, allow_fixture=False, now=NOW
    )
    assert result["p66_operator_activation_intake_valid"] is True
    assert result["eligible_for_separate_external_order_test_execution_step"] is True
    assert result["real_order_test_execution_performed"] is False


def test_p66_blocks_phrase_scope_and_runtime_authority():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    actual = _actual_from_fixture(
        fixture,
        operator_phrase="BAD",
        execution_scope="wrong",
        runtime_authority_granted=True,
    )
    result = validate_p66_operator_activation_intake(actual, source, require_approved=True, now=NOW)
    assert result["p66_operator_activation_intake_valid"] is False
    assert "P66_OPERATOR_PHRASE_MISMATCH" in result["p66_operator_activation_intake_block_reasons"]
    assert "P66_APPROVED_SCOPE_REQUIRED" in result["p66_operator_activation_intake_block_reasons"]
    assert "P66_EXPECTED_FALSE:runtime_authority_granted" in result["p66_operator_activation_intake_block_reasons"]


def test_p66_blocks_mainnet_submit_path_and_wrong_symbol():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    actual = _actual_from_fixture(
        fixture,
        base_url="https://fapi.binance.com",
        path="/fapi/v1/order",
        symbol="ETHUSDT",
    )
    result = validate_p66_operator_activation_intake(actual, source, require_approved=True, now=NOW)
    assert "P66_BASE_URL_NOT_TESTNET" in result["p66_operator_activation_intake_block_reasons"]
    assert "P66_PATH_NOT_ORDER_TEST" in result["p66_operator_activation_intake_block_reasons"]
    assert "P66_SYMBOL_NOT_ALLOWED" in result["p66_operator_activation_intake_block_reasons"]


def test_p66_blocks_secret_field_invalid_fingerprint_and_zero_nonce():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    actual = _actual_from_fixture(fixture, key_fingerprint_sha256="bad", one_shot_nonce_sha256="0" * 64)
    actual["api_secret_value"] = "forbidden"
    result = validate_p66_operator_activation_intake(actual, source, require_approved=True, now=NOW)
    assert result["p66_operator_activation_intake_valid"] is False
    assert "P66_KEY_FINGERPRINT_REQUIRED" in result["p66_operator_activation_intake_block_reasons"]
    assert "P66_ONE_SHOT_NONCE_REQUIRED" in result["p66_operator_activation_intake_block_reasons"]
    assert any("P66_FORBIDDEN_SECRET_OR_RAW_FIELD" in reason for reason in result["p66_operator_activation_intake_block_reasons"])


def test_p66_blocks_expired_and_duplicate_nonce():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    expired = _actual_from_fixture(
        fixture,
        created_at_utc="2026-07-12T03:30:00Z",
        expires_at_utc="2026-07-12T03:45:00Z",
    )
    result = validate_p66_operator_activation_intake(expired, source, require_approved=True, now=NOW)
    assert "P66_INTAKE_EXPIRED" in result["p66_operator_activation_intake_block_reasons"]

    actual = _actual_from_fixture(fixture)
    duplicate = validate_p66_operator_activation_intake(
        actual,
        source,
        require_approved=True,
        seen_nonce_hashes={actual["one_shot_nonce_sha256"]},
        now=NOW,
    )
    assert "P66_ONE_SHOT_NONCE_ALREADY_SEEN" in duplicate["p66_operator_activation_intake_block_reasons"]


def test_p66_receipt_never_executes_or_consumes_nonce():
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    validation = validate_p66_operator_activation_intake(
        fixture, source, require_approved=True, allow_fixture=True, now=NOW
    )
    receipt = build_p66_activation_validation_receipt(fixture, validation, fixture_validation_only=True)
    assert receipt["accepted"] is True
    assert receipt["eligible_for_separate_external_order_test_execution_step"] is False
    assert receipt["one_shot_nonce_consumed_by_p66"] is False
    assert receipt["real_order_test_execution_performed_by_p66"] is False


def test_p66_negative_fixtures_all_blocked():
    result = build_p66_negative_fixture_results(_source(), now=NOW)
    assert result["all_negative_fixtures_blocked"] is True
    assert result["case_count"] == 12


def test_p66_report_ready_no_actual_operator_or_call():
    report = build_p66_operator_activation_intake_report(_source(), now=NOW)
    assert report["status"] == STATUS_P66_READY
    assert report["approved_fixture_validation_passed"] is True
    assert report["actual_operator_activation_received"] is False
    assert report["real_order_test_endpoint_call_performed"] is False
    assert report["actual_order_submission_performed"] is False


def test_p66_validate_file_and_persist_outputs(tmp_path: Path):
    source = _source()
    fixture = build_valid_p66_operator_activation_intake_fixture(source, now=NOW)
    actual = _actual_from_fixture(fixture, operator_request_id="operator-request-file")
    intake_path = tmp_path / "intake.json"
    p65_path = tmp_path / "p65.json"
    atomic_write_json(intake_path, actual)
    atomic_write_json(p65_path, source)
    validation, receipt = validate_p66_intake_file(intake_path, p65_path, now=NOW)
    assert validation["p66_operator_activation_intake_valid"] is True
    assert receipt["accepted"] is True
    assert receipt["real_order_test_execution_performed_by_p66"] is False

    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "p65_operator_installed_testnet_sender_executable_report.json", source)
    report = persist_p66_operator_activation_intake_for_real_order_test(tmp_path)
    assert report["status"] == STATUS_P66_READY
    assert (latest / "p66_operator_activation_intake_for_real_order_test_report.json").exists()
    assert (latest / "p66_operator_activation_intake_TEMPLATE_REVIEW_ONLY_NO_CALL.json").exists()
    assert (tmp_path / "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_REPORT.md").exists()
