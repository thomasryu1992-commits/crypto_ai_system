from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_runtime_authority_bridge import (
    REMAINING_RUNTIME_AUTHORITY_BLOCKERS,
    RUNTIME_AUTHORITY_REQUIREMENTS,
    STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED,
    build_phase9_2_runtime_authority_bridge_report,
    persist_phase9_2_runtime_authority_bridge_report,
    validate_phase9_2_runtime_authority_bridge,
)
from tests.agents.test_phase9_2_real_submit_enablement_gate import _write_ready_phase9_3_sources


def _write_ready_real_submit_gate_sources() -> None:
    _write_ready_phase9_3_sources()
    from crypto_ai_system.validation.phase9_2_real_submit_enablement_gate import persist_phase9_2_real_submit_enablement_gate_report

    persist_phase9_2_real_submit_enablement_gate_report(run_phase9_3_design_first=False)


def test_phase9_2_runtime_authority_bridge_records_requirements_still_disabled() -> None:
    _write_ready_real_submit_gate_sources()
    cfg = load_config()
    report, bridge, validation_report, negative_fixture_results = build_phase9_2_runtime_authority_bridge_report(
        cfg=cfg,
        run_real_submit_gate_first=False,
    )

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["still_disabled"] is True
    assert report["phase9_2_runtime_authority_bridge_recorded"] is True
    assert report["runtime_authority_preconditions_ready_for_manual_design_review"] is True
    assert report["runtime_authority_granted"] is False
    assert report["runtime_authority_bridge_complete"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    for blocker in REMAINING_RUNTIME_AUTHORITY_BLOCKERS:
        assert blocker in report["block_reasons"]
    for requirement in RUNTIME_AUTHORITY_REQUIREMENTS:
        assert requirement in bridge["runtime_authority_requirements"]
    assert bridge["artifact_type"] == "phase9_2_runtime_authority_bridge_review_only"
    assert bridge["operator_approval_fixture_is_not_runtime_authority"] is True
    assert bridge["secret_manager_runtime_binding_performed"] is False
    assert bridge["signed_testnet_executor_enabled"] is False
    assert bridge["endpoint_policy_changed"] is False
    assert bridge["order_endpoint_called"] is False
    assert bridge["http_request_sent"] is False
    assert bridge["signature_created"] is False
    assert validation_report["phase9_2_runtime_authority_bridge_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_2_runtime_authority_bridge_validator_blocks_runtime_authority_opening() -> None:
    _write_ready_real_submit_gate_sources()
    cfg = load_config()
    _report, bridge, _validation_report, _negative_fixture_results = build_phase9_2_runtime_authority_bridge_report(
        cfg=cfg,
        run_real_submit_gate_first=False,
    )
    bridge.update(
        {
            "runtime_authority_granted": True,
            "runtime_authority_bridge_complete": True,
            "secret_manager_runtime_binding_performed": True,
            "signed_testnet_executor_enabled": True,
            "endpoint_policy_changed": True,
            "phase9_2_order_submission_authorized": True,
            "order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
        }
    )

    result = validate_phase9_2_runtime_authority_bridge(bridge)

    assert result["phase9_2_runtime_authority_bridge_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "runtime_authority_granted" in result["unsafe_truthy_fields"]
    assert "secret_manager_runtime_binding_performed" in result["unsafe_truthy_fields"]
    assert "signed_testnet_executor_enabled" in result["unsafe_truthy_fields"]
    assert "endpoint_policy_changed" in result["unsafe_truthy_fields"]
    assert "PHASE9_2_RUNTIME_AUTHORITY_GRANTED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_RUNTIME_AUTHORITY_SECRET_BINDING_PERFORMED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_RUNTIME_AUTHORITY_EXECUTOR_ENABLED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_RUNTIME_AUTHORITY_ENDPOINT_POLICY_CHANGED_UNEXPECTED" in result["block_reasons"]


def test_phase9_2_runtime_authority_bridge_persist_writes_review_only_artifacts() -> None:
    _write_ready_real_submit_gate_sources()
    report = persist_phase9_2_runtime_authority_bridge_report(run_real_submit_gate_first=False)

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_RECORDED_STILL_DISABLED
    assert Path("storage/latest/phase9_2_runtime_authority_bridge_report.json").exists()
    assert Path("storage/latest/runtime_authority_bridge_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_bridge_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_runtime_authority_bridge_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_RUNTIME_AUTHORITY_BRIDGE_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/runtime_authority_bridge_STILL_DISABLED_REVIEW_ONLY.json").exists()
