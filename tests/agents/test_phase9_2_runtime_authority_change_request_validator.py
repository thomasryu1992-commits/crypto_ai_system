from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request_validator import (
    REMAINING_VALIDATOR_BLOCKERS,
    RUNTIME_AUTHORITY_REQUEST_REQUIRED_FIELDS,
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED,
    build_operator_filled_change_request_fixture,
    build_phase9_2_runtime_authority_change_request_validator_report,
    persist_phase9_2_runtime_authority_change_request_validator_report,
    validate_operator_filled_runtime_authority_change_request,
)


def _write_ready_runtime_authority_change_request_sources() -> None:
    from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import persist_phase9_2_runtime_authority_change_request_report

    persist_phase9_2_runtime_authority_change_request_report(run_runtime_authority_bridge_first=True)


def test_phase9_2_runtime_authority_change_request_validator_records_still_disabled() -> None:
    _write_ready_runtime_authority_change_request_sources()
    cfg = load_config()
    report, operator_fixture, operator_fixture_validation, negative_fixture_results = build_phase9_2_runtime_authority_change_request_validator_report(
        cfg=cfg,
        run_change_request_first=False,
    )

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["still_disabled"] is True
    assert report["phase9_2_runtime_authority_change_request_validator_recorded"] is True
    assert report["operator_filled_request_field_level_valid"] is True
    assert report["operator_filled_request_fixture_is_runtime_authority"] is False
    assert report["validator_grants_runtime_authority"] is False
    assert report["runtime_authority_granted"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    for blocker in REMAINING_VALIDATOR_BLOCKERS:
        assert blocker in report["block_reasons"]
    assert operator_fixture["artifact_type"] == "phase9_2_operator_filled_runtime_authority_change_request_fixture_review_only"
    for field in RUNTIME_AUTHORITY_REQUEST_REQUIRED_FIELDS:
        assert field in operator_fixture
    assert operator_fixture["metadata_only_testnet_key_fingerprint_sha256"]
    assert operator_fixture["secret_manager_runtime_binding_performed"] is False
    assert operator_fixture["signed_testnet_executor_enabled"] is False
    assert operator_fixture["endpoint_policy_changed"] is False
    assert operator_fixture["phase9_2_order_submission_authorized"] is False
    assert operator_fixture_validation["phase9_2_operator_filled_request_field_level_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_2_runtime_authority_change_request_validator_blocks_placeholder_values() -> None:
    _write_ready_runtime_authority_change_request_sources()
    cfg = load_config()
    _report, operator_fixture, _validation, _negative = build_phase9_2_runtime_authority_change_request_validator_report(
        cfg=cfg,
        run_change_request_first=False,
    )
    operator_fixture.update(
        {
            "operator_signature": "OPERATOR_SIGNATURE_REQUIRED",
            "operator_change_ticket_or_record_id": "TODO_CHANGE_TICKET_REQUIRED",
            "metadata_only_testnet_key_fingerprint_sha256": "KEY_FINGERPRINT_PLACEHOLDER",
        }
    )

    result = validate_operator_filled_runtime_authority_change_request(operator_fixture)

    assert result["phase9_2_operator_filled_request_field_level_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE9_2_VALIDATOR_PLACEHOLDER_VALUE:operator_signature" in result["block_reasons"]
    assert "PHASE9_2_VALIDATOR_PLACEHOLDER_VALUE:operator_change_ticket_or_record_id" in result["block_reasons"]
    assert "PHASE9_2_VALIDATOR_TESTNET_KEY_FINGERPRINT_INVALID" in result["block_reasons"]


def test_phase9_2_runtime_authority_change_request_validator_blocks_runtime_authority_attempts() -> None:
    _write_ready_runtime_authority_change_request_sources()
    cfg = load_config()
    _report, operator_fixture, _validation, _negative = build_phase9_2_runtime_authority_change_request_validator_report(
        cfg=cfg,
        run_change_request_first=False,
    )
    operator_fixture.update(
        {
            "runtime_authority_granted": True,
            "runtime_authority_validator_approved": True,
            "secret_manager_runtime_binding_performed": True,
            "signed_testnet_executor_enabled": True,
            "endpoint_policy_changed": True,
            "phase9_2_order_submission_authorized": True,
            "order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
            "api_secret": "raw-secret-value-should-block",
        }
    )

    result = validate_operator_filled_runtime_authority_change_request(operator_fixture)

    assert result["phase9_2_operator_filled_request_field_level_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "runtime_authority_granted" in result["unsafe_truthy_fields"]
    assert "runtime_authority_validator_approved" in result["unsafe_truthy_fields"]
    assert "secret_manager_runtime_binding_performed" in result["unsafe_truthy_fields"]
    assert "signed_testnet_executor_enabled" in result["unsafe_truthy_fields"]
    assert "endpoint_policy_changed" in result["unsafe_truthy_fields"]
    assert result["secret_like_value_paths"]
    assert any(reason.startswith("PHASE9_2_VALIDATOR_SECRET_LIKE_VALUES_PRESENT") for reason in result["block_reasons"])


def test_phase9_2_runtime_authority_change_request_validator_negative_fixtures_are_complete() -> None:
    _write_ready_runtime_authority_change_request_sources()
    cfg = load_config()
    _report, _operator_fixture, _validation, negative_fixture_results = build_phase9_2_runtime_authority_change_request_validator_report(
        cfg=cfg,
        run_change_request_first=False,
    )

    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    fixture_results = negative_fixture_results["fixture_results"]
    for fixture_name in [
        "placeholder_operator_signature",
        "missing_operator_change_ticket",
        "placeholder_key_fingerprint",
        "raw_secret_value_present",
        "mainnet_key_scope_allowed",
        "max_order_count_gt_one",
        "max_notional_too_large",
        "daily_loss_cap_too_large",
        "kill_switch_not_confirmed",
        "secret_binding_already_performed",
        "executor_enabled_true",
        "endpoint_policy_changed_true",
        "order_submission_authorized_true",
        "order_endpoint_called_true",
        "signature_created_true",
        "http_request_sent_true",
    ]:
        assert fixture_name in fixture_results
        assert fixture_results[fixture_name]["blocked"] is True
        assert fixture_results[fixture_name]["fail_closed"] is True
        assert fixture_results[fixture_name]["block_reasons"]


def test_phase9_2_runtime_authority_change_request_validator_persist_writes_review_only_artifacts() -> None:
    _write_ready_runtime_authority_change_request_sources()
    report = persist_phase9_2_runtime_authority_change_request_validator_report(run_change_request_first=False)

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_RECORDED_STILL_DISABLED
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_validator_report.json").exists()
    assert Path("storage/latest/runtime_authority_change_request_OPERATOR_FILLED_FIXTURE_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_operator_values_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_validator_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_VALIDATOR_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase9_2_runtime_authority_change_request_validator_report.json").exists()
