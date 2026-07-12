from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY,
    build_phase9_1_actual_operator_approval_intake_hardening_report,
    persist_phase9_1_actual_operator_approval_intake_hardening_report,
    validate_phase9_1_actual_operator_approval_intake_template,
)
from tests.agents.test_phase9_1_single_signed_testnet_enablement_intake import _write_ready_phase8_4_sources


def _write_ready_phase9_1_sources() -> None:
    _write_ready_phase8_4_sources()
    cfg = load_config()
    # The hardening builder can generate the baseline Phase 9.1 intake itself.
    from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
        persist_phase9_1_single_signed_testnet_enablement_intake_report,
    )

    persist_phase9_1_single_signed_testnet_enablement_intake_report(cfg=cfg, run_phase8_4_first=False)


def test_phase9_1_hardening_builds_actual_operator_approval_template_still_disabled() -> None:
    _write_ready_phase9_1_sources()
    cfg = load_config()
    report, template, validation_report, negative_fixture_results = build_phase9_1_actual_operator_approval_intake_hardening_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )

    assert report["status"] == STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase9_1_actual_operator_approval_template_ready"] is True
    assert report["phase9_1_actual_operator_approval_values_complete"] is False
    assert report["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert template["actual_approval_intake_type"] == "phase9_1_actual_operator_approval_intake_template_review_only"
    assert template["operator_decision"] == "pending_explicit_manual_approval"
    assert template["single_order_scope"] is True
    assert template["max_order_count"] == 1
    assert template["testnet_key_scope"]["live_mainnet_key_prohibited"] is True
    assert template["testnet_key_scope"]["withdrawal_permission_allowed"] is False
    assert template["testnet_key_scope"]["transfer_permission_allowed"] is False
    assert template["testnet_key_scope"]["admin_permission_allowed"] is False
    assert validation_report["phase9_1_actual_operator_approval_template_valid_review_only"] is True
    assert validation_report["phase9_1_actual_operator_approval_values_complete"] is False
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, template, validation_report, negative_fixture_results):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["actual_order_submission_performed"] is False


def test_phase9_1_hardening_persist_writes_actual_approval_artifacts() -> None:
    _write_ready_phase9_1_sources()
    report = persist_phase9_1_actual_operator_approval_intake_hardening_report(run_phase9_1_first=False)

    assert report["status"] == STATUS_ACTUAL_APPROVAL_HARDENED_REVIEW_ONLY
    assert Path("storage/latest/phase9_1_actual_operator_approval_hardening_report.json").exists()
    assert Path("storage/latest/phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_1_actual_operator_approval_intake_validation_report.json").exists()
    assert Path("storage/latest/phase9_1_actual_operator_approval_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_1_ACTUAL_OPERATOR_APPROVAL_INTAKE_HARDENING_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json").exists()
    assert Path("storage/phase9_1_single_signed_testnet_enablement_intake/phase9_1_actual_operator_approval_hardening_report.json").exists()


def test_phase9_1_actual_approval_validator_blocks_unsafe_scope_secret_and_flags() -> None:
    _write_ready_phase9_1_sources()
    cfg = load_config()
    _report, template, _validation_report, _fixtures = build_phase9_1_actual_operator_approval_intake_hardening_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )
    template["max_order_count"] = 2
    template["small_max_notional"] = "1000.0"
    template["testnet_key_scope"]["live_mainnet_key_prohibited"] = False
    template["testnet_key_scope"]["withdrawal_permission_allowed"] = True
    template["api_secret_value"] = "raw-secret-value-must-not-appear"
    template["testnet_order_submission_allowed"] = True

    result = validate_phase9_1_actual_operator_approval_intake_template(template)

    assert result["phase9_1_actual_operator_approval_template_valid_review_only"] is False
    assert result["phase9_1_actual_operator_approval_template_blocked_fail_closed"] is True
    blockers = result["phase9_1_actual_operator_approval_validation_blockers"]
    assert "PHASE9_1_ACTUAL_APPROVAL_MAX_ORDER_COUNT_NOT_ONE" in blockers
    assert "PHASE9_1_ACTUAL_APPROVAL_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH" in blockers
    assert "PHASE9_1_ACTUAL_APPROVAL_KEY_SCOPE_TRUE_REQUIRED:live_mainnet_key_prohibited" in blockers
    assert "PHASE9_1_ACTUAL_APPROVAL_KEY_SCOPE_FALSE_REQUIRED:withdrawal_permission_allowed" in blockers
    assert any(item.startswith("SECRET_LIKE_FIELDS_PRESENT:") for item in blockers)
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]


def test_phase9_1_actual_approval_complete_values_validate_but_do_not_enable_submit() -> None:
    _write_ready_phase9_1_sources()
    cfg = load_config()
    _report, template, _validation_report, _fixtures = build_phase9_1_actual_operator_approval_intake_hardening_report(
        cfg=cfg,
        run_phase9_1_first=False,
    )
    template.update(
        {
            "operator_decision": "approve_single_signed_testnet_order",
            "operator_signature": "operator_signature_fixture",
            "operator_signature_hash_sha256": "b" * 64,
            "actual_operator_approval_recorded": True,
            "operator_approval_ticket_or_record_id": "ticket-phase9-1-fixture",
            "operator_approval_timestamp_utc": "2026-01-01T00:00:00Z",
            "kill_switch_confirmed_for_actual_approval": True,
            "kill_switch_confirmation_timestamp_utc": "2026-01-01T00:00:00Z",
            "testnet_key_fingerprint_sha256": "a" * 64,
        }
    )

    result = validate_phase9_1_actual_operator_approval_intake_template(template, require_complete_approval=True)

    assert result["phase9_1_actual_operator_approval_template_valid_review_only"] is True
    assert result["phase9_1_actual_operator_approval_values_complete"] is True
    assert result["phase9_1_actual_operator_approval_blockers"] == []
    assert result["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert result["testnet_order_submission_allowed"] is False
    assert result["actual_order_submission_performed"] is False
