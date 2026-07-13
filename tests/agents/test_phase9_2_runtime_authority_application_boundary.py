from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_runtime_authority_application_boundary import (
    APPLICATION_BOUNDARY_REQUIRED_FIELDS,
    REMAINING_APPLICATION_BOUNDARY_BLOCKERS,
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED,
    build_phase9_2_runtime_authority_application_boundary_report,
    persist_phase9_2_runtime_authority_application_boundary_report,
    validate_runtime_authority_application_boundary_template,
)


def _write_ready_validator_sources() -> None:
    from crypto_ai_system.validation.phase9_2_runtime_authority_change_request_validator import (
        persist_phase9_2_runtime_authority_change_request_validator_report,
    )

    persist_phase9_2_runtime_authority_change_request_validator_report(run_change_request_first=True)


def test_phase9_2_runtime_authority_application_boundary_records_still_disabled() -> None:
    _write_ready_validator_sources()
    cfg = load_config()
    report, template, validation, negative_fixture_results = build_phase9_2_runtime_authority_application_boundary_report(
        cfg=cfg,
        run_validator_first=False,
    )

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["still_disabled"] is True
    assert report["phase9_2_runtime_authority_application_boundary_recorded"] is True
    assert report["runtime_authority_application_boundary_template_valid"] is True
    assert report["runtime_authority_application_boundary_complete"] is False
    assert report["runtime_authority_application_approved"] is False
    assert report["runtime_authority_application_performed"] is False
    assert report["runtime_authority_granted"] is False
    assert report["secret_manager_runtime_binding_performed"] is False
    assert report["executor_policy_application_performed"] is False
    assert report["endpoint_policy_application_performed"] is False
    assert report["signed_testnet_executor_enabled"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    for blocker in REMAINING_APPLICATION_BOUNDARY_BLOCKERS:
        assert blocker in report["block_reasons"]
    assert template["artifact_type"] == "phase9_2_runtime_authority_application_boundary_template_still_disabled_review_only"
    for field in APPLICATION_BOUNDARY_REQUIRED_FIELDS:
        assert field in template
    assert template["real_operator_approval_record_required"] is True
    assert template["real_operator_approval_record_present"] is False
    assert template["fresh_preorder_risk_gate_refresh_required_at_endpoint_time"] is True
    assert template["fresh_preorder_risk_gate_refresh_performed_at_endpoint_time"] is False
    assert template["secret_manager_runtime_binding_performed"] is False
    assert template["executor_policy_application_performed"] is False
    assert template["endpoint_policy_application_performed"] is False
    assert template["idempotency_key_bound_to_real_order"] is False
    assert validation["phase9_2_runtime_authority_application_boundary_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_2_runtime_authority_application_boundary_blocks_application_attempts() -> None:
    _write_ready_validator_sources()
    cfg = load_config()
    _report, template, _validation, _negative = build_phase9_2_runtime_authority_application_boundary_report(
        cfg=cfg,
        run_validator_first=False,
    )
    template.update(
        {
            "runtime_authority_application_performed": True,
            "runtime_authority_granted": True,
            "secret_manager_runtime_binding_performed": True,
            "executor_policy_application_performed": True,
            "endpoint_policy_application_performed": True,
            "signed_testnet_executor_enabled": True,
            "endpoint_policy_changed": True,
            "phase9_2_order_submission_authorized": True,
            "order_endpoint_called": True,
            "signature_created": True,
            "http_request_sent": True,
        }
    )

    result = validate_runtime_authority_application_boundary_template(template)

    assert result["phase9_2_runtime_authority_application_boundary_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "runtime_authority_application_performed" in result["unsafe_truthy_fields"]
    assert "runtime_authority_granted" in result["unsafe_truthy_fields"]
    assert "secret_manager_runtime_binding_performed" in result["unsafe_truthy_fields"]
    assert "executor_policy_application_performed" in result["unsafe_truthy_fields"]
    assert "endpoint_policy_application_performed" in result["unsafe_truthy_fields"]
    assert "signed_testnet_executor_enabled" in result["unsafe_truthy_fields"]
    assert "endpoint_policy_changed" in result["unsafe_truthy_fields"]
    assert "phase9_2_order_submission_authorized" in result["unsafe_truthy_fields"]
    assert any(reason.startswith("PHASE9_2_APPLICATION_BOUNDARY_UNSAFE_FLAGS") for reason in result["block_reasons"])


def test_phase9_2_runtime_authority_application_boundary_blocks_secret_like_values_and_bad_caps() -> None:
    _write_ready_validator_sources()
    cfg = load_config()
    _report, template, _validation, _negative = build_phase9_2_runtime_authority_application_boundary_report(
        cfg=cfg,
        run_validator_first=False,
    )
    template.update(
        {
            "api_secret": "raw-secret-value-should-block",
            "max_order_count": 3,
            "small_max_notional_usd": 250.0,
            "daily_loss_cap_usd": 250.0,
        }
    )

    result = validate_runtime_authority_application_boundary_template(template)

    assert result["phase9_2_runtime_authority_application_boundary_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert result["secret_like_value_paths"]
    assert "PHASE9_2_APPLICATION_BOUNDARY_MAX_ORDER_COUNT_NOT_ONE" in result["block_reasons"]
    assert "PHASE9_2_APPLICATION_BOUNDARY_MAX_NOTIONAL_EXCEEDS_SMALL_CAP" in result["block_reasons"]
    assert "PHASE9_2_APPLICATION_BOUNDARY_DAILY_LOSS_CAP_EXCEEDS_LIMIT" in result["block_reasons"]
    assert any(reason.startswith("PHASE9_2_APPLICATION_BOUNDARY_SECRET_LIKE_VALUES_PRESENT") for reason in result["block_reasons"])


def test_phase9_2_runtime_authority_application_boundary_negative_fixtures_are_complete() -> None:
    _write_ready_validator_sources()
    cfg = load_config()
    _report, _template, _validation, negative_fixture_results = build_phase9_2_runtime_authority_application_boundary_report(
        cfg=cfg,
        run_validator_first=False,
    )

    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    fixture_results = negative_fixture_results["fixture_results"]
    for fixture_name in [
        "missing_source_validator_hash",
        "real_operator_approval_present_true",
        "fresh_risk_refresh_performed_true",
        "secret_binding_performed_true",
        "executor_policy_application_performed_true",
        "endpoint_policy_application_performed_true",
        "runtime_authority_application_performed_true",
        "runtime_authority_granted_true",
        "signed_testnet_executor_enabled_true",
        "endpoint_policy_changed_true",
        "order_submission_authorized_true",
        "idempotency_bound_to_real_order_true",
        "max_order_count_gt_one",
        "max_notional_too_large",
        "daily_loss_cap_too_large",
        "raw_secret_value_present",
        "order_endpoint_called_true",
        "signature_created_true",
        "http_request_sent_true",
    ]:
        assert fixture_name in fixture_results
        assert fixture_results[fixture_name]["blocked"] is True
        assert fixture_results[fixture_name]["fail_closed"] is True
        assert fixture_results[fixture_name]["block_reasons"]


def test_phase9_2_runtime_authority_application_boundary_persist_writes_review_only_artifacts() -> None:
    _write_ready_validator_sources()
    report = persist_phase9_2_runtime_authority_application_boundary_report(run_validator_first=False)

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_RECORDED_STILL_DISABLED
    assert Path("storage/latest/phase9_2_runtime_authority_application_boundary_report.json").exists()
    assert Path("storage/latest/runtime_authority_application_boundary_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_application_boundary_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_application_boundary_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_RUNTIME_AUTHORITY_APPLICATION_BOUNDARY_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase9_2_runtime_authority_application_boundary_report.json").exists()
