from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_runtime_authority_change_request import (
    CHANGE_REQUEST_REQUIRED_FIELDS,
    REMAINING_CHANGE_REQUEST_BLOCKERS,
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED,
    build_phase9_2_runtime_authority_change_request_report,
    persist_phase9_2_runtime_authority_change_request_report,
    validate_phase9_2_runtime_authority_change_request,
)
from tests.agents.test_phase9_2_runtime_authority_bridge import _write_ready_real_submit_gate_sources


def _write_ready_runtime_authority_bridge_sources() -> None:
    _write_ready_real_submit_gate_sources()
    from crypto_ai_system.validation.phase9_2_runtime_authority_bridge import persist_phase9_2_runtime_authority_bridge_report

    persist_phase9_2_runtime_authority_bridge_report(run_real_submit_gate_first=False)


def test_phase9_2_runtime_authority_change_request_records_template_still_disabled() -> None:
    _write_ready_runtime_authority_bridge_sources()
    cfg = load_config()
    report, template, validation_report, negative_fixture_results = build_phase9_2_runtime_authority_change_request_report(
        cfg=cfg,
        run_runtime_authority_bridge_first=False,
    )

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["still_disabled"] is True
    assert report["phase9_2_runtime_authority_change_request_recorded"] is True
    assert report["runtime_authority_change_request_template_ready_for_manual_review"] is True
    assert report["runtime_authority_change_request_approved"] is False
    assert report["runtime_authority_granted"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    for blocker in REMAINING_CHANGE_REQUEST_BLOCKERS:
        assert blocker in report["block_reasons"]
    assert template["artifact_type"] == "phase9_2_runtime_authority_change_request_template_review_only"
    for field in CHANGE_REQUEST_REQUIRED_FIELDS:
        assert field in template
    assert template["source_phase9_2_runtime_authority_bridge_id"]
    assert template["source_phase9_2_runtime_authority_bridge_hash"]
    assert template["single_order_runtime_scope"] is True
    assert template["max_order_count"] == 1
    assert template["small_max_notional_usd"] <= 10.0
    assert template["mainnet_key_scope_allowed"] is False
    assert template["secret_manager_runtime_binding_performed"] is False
    assert template["signed_testnet_executor_enabled"] is False
    assert template["endpoint_policy_changed"] is False
    assert template["order_endpoint_called"] is False
    assert template["http_request_sent"] is False
    assert template["signature_created"] is False
    assert validation_report["phase9_2_runtime_authority_change_request_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_2_runtime_authority_change_request_validator_blocks_unsafe_runtime_change() -> None:
    _write_ready_runtime_authority_bridge_sources()
    cfg = load_config()
    _report, template, _validation_report, _negative_fixture_results = build_phase9_2_runtime_authority_change_request_report(
        cfg=cfg,
        run_runtime_authority_bridge_first=False,
    )
    template.update(
        {
            "runtime_authority_change_request_approved": True,
            "runtime_authority_granted": True,
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

    result = validate_phase9_2_runtime_authority_change_request(template)

    assert result["phase9_2_runtime_authority_change_request_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "runtime_authority_granted" in result["unsafe_truthy_fields"]
    assert "secret_manager_runtime_binding_performed" in result["unsafe_truthy_fields"]
    assert "signed_testnet_executor_enabled" in result["unsafe_truthy_fields"]
    assert "endpoint_policy_changed" in result["unsafe_truthy_fields"]
    assert result["secret_like_value_paths"]
    assert "PHASE9_2_CHANGE_REQUEST_APPROVED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_CHANGE_REQUEST_RUNTIME_AUTHORITY_GRANTED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_CHANGE_REQUEST_SECRET_BINDING_PERFORMED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_CHANGE_REQUEST_EXECUTOR_ENABLED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_CHANGE_REQUEST_ENDPOINT_POLICY_CHANGED_UNEXPECTED" in result["block_reasons"]


def test_phase9_2_runtime_authority_change_request_negative_fixtures_are_complete() -> None:
    _write_ready_runtime_authority_bridge_sources()
    cfg = load_config()
    _report, _template, _validation_report, negative_fixture_results = build_phase9_2_runtime_authority_change_request_report(
        cfg=cfg,
        run_runtime_authority_bridge_first=False,
    )

    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    fixture_results = negative_fixture_results["fixture_results"]
    for fixture_name in [
        "missing_source_bridge_hash",
        "runtime_authority_change_request_approved_true",
        "runtime_authority_granted_true",
        "secret_manager_runtime_binding_performed_true",
        "signed_testnet_executor_enabled_true",
        "endpoint_policy_changed_true",
        "order_submission_authorized_true",
        "raw_secret_value_present",
        "missing_operator_change_ticket",
        "max_order_count_gt_one",
        "mainnet_key_scope_allowed",
        "order_endpoint_called_true",
    ]:
        assert fixture_name in fixture_results
        assert fixture_results[fixture_name]["blocked"] is True
        assert fixture_results[fixture_name]["fail_closed"] is True
        assert fixture_results[fixture_name]["block_reasons"]


def test_phase9_2_runtime_authority_change_request_persist_writes_review_only_artifacts() -> None:
    _write_ready_runtime_authority_bridge_sources()
    report = persist_phase9_2_runtime_authority_change_request_report(run_runtime_authority_bridge_first=False)

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_RECORDED_STILL_DISABLED
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_report.json").exists()
    assert Path("storage/latest/runtime_authority_change_request_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_change_request_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_RUNTIME_AUTHORITY_CHANGE_REQUEST_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/runtime_authority_change_request_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json").exists()
