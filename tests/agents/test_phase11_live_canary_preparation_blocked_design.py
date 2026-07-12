from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase11_live_canary_preparation_blocked_design import (
    LIVE_CANARY_APPROVAL_FIELDS_REQUIRED,
    LIVE_KEY_SCOPE_CHECKS_REQUIRED,
    LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED,
    STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY,
    build_phase11_live_canary_preparation_blocked_design_report,
    persist_phase11_live_canary_preparation_blocked_design_report,
    validate_phase11_live_canary_preparation_design,
)
from tests.agents.test_phase10_signed_testnet_session_validation_blocked_design import _write_ready_phase9_4_sources


def _write_ready_phase10_sources() -> None:
    _write_ready_phase9_4_sources()
    from crypto_ai_system.validation.phase10_signed_testnet_session_validation_blocked_design import (
        persist_phase10_signed_testnet_session_validation_blocked_design_report,
    )

    persist_phase10_signed_testnet_session_validation_blocked_design_report(run_phase9_3_9_4_first=False)


def test_phase11_live_canary_preparation_records_blocked_design() -> None:
    _write_ready_phase10_sources()
    cfg = load_config()
    report, design, validation, negative_fixture_results = build_phase11_live_canary_preparation_blocked_design_report(
        cfg=cfg,
        run_phase10_first=False,
    )

    assert report["status"] == STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase11_live_canary_preparation_design_recorded"] is True
    assert report["phase11_live_canary_preparation_design_valid"] is True
    assert report["live_canary_preparation_may_begin"] is False
    assert report["live_read_only_probe_performed"] is False
    assert report["live_key_scope_validation_performed"] is False
    assert report["live_canary_approval_packet_created"] is False
    assert report["live_canary_execution_enabled"] is False
    assert report["live_scaled_execution_enabled"] is False
    assert "PHASE11_BLOCKED_UNTIL_PHASE10_MULTIPLE_CLEAN_SIGNED_TESTNET_SESSIONS_EXIST" in report["block_reasons"]
    assert validation["phase11_live_canary_preparation_design_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for check in LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED:
        assert check in design["required_live_read_only_probe_checks"]
        assert check in design["live_read_only_probe_plan"]
    for check in LIVE_KEY_SCOPE_CHECKS_REQUIRED:
        assert check in design["required_live_key_scope_checks"]
        assert check in design["live_key_scope_validation_plan"]
    for field in LIVE_CANARY_APPROVAL_FIELDS_REQUIRED:
        assert field in design["required_live_canary_approval_fields"]


def test_phase11_validator_blocks_live_canary_activation_or_probe_execution() -> None:
    _write_ready_phase10_sources()
    cfg = load_config()
    _report, design, _validation, _negative_fixture_results = build_phase11_live_canary_preparation_blocked_design_report(
        cfg=cfg,
        run_phase10_first=False,
    )
    design["live_canary_preparation_may_begin"] = True
    design["live_read_only_probe_performed"] = True
    design["live_key_scope_validation_performed"] = True
    design["live_canary_execution_enabled"] = True

    result = validate_phase11_live_canary_preparation_design(design)

    assert result["phase11_live_canary_preparation_design_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE11_LIVE_CANARY_PREPARATION_UNSAFE_FIELD:live_canary_preparation_may_begin" in result["block_reasons"]
    assert "PHASE11_LIVE_CANARY_PREPARATION_UNSAFE_FIELD:live_canary_execution_enabled" in result["block_reasons"]
    assert "live_canary_preparation_may_begin" in result["unsafe_truthy_fields"]


def test_phase11_validator_requires_live_probe_key_scope_and_approval_fields() -> None:
    _write_ready_phase10_sources()
    cfg = load_config()
    _report, design, _validation, _negative_fixture_results = build_phase11_live_canary_preparation_blocked_design_report(
        cfg=cfg,
        run_phase10_first=False,
    )
    design["required_live_read_only_probe_checks"] = [c for c in LIVE_READ_ONLY_PROBE_CHECKS_REQUIRED if c != "fee_tier"]
    design["required_live_key_scope_checks"] = [c for c in LIVE_KEY_SCOPE_CHECKS_REQUIRED if c != "withdrawal_disabled"]
    design["required_live_canary_approval_fields"] = [f for f in LIVE_CANARY_APPROVAL_FIELDS_REQUIRED if f != "manual_kill_switch"]

    result = validate_phase11_live_canary_preparation_design(design)

    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE11_LIVE_READ_ONLY_PROBE_CHECK_MISSING:fee_tier" in result["block_reasons"]
    assert "PHASE11_LIVE_KEY_SCOPE_CHECK_MISSING:withdrawal_disabled" in result["block_reasons"]
    assert "PHASE11_LIVE_CANARY_APPROVAL_FIELD_MISSING:manual_kill_switch" in result["block_reasons"]


def test_phase11_persist_writes_latest_live_canary_and_registry_artifacts() -> None:
    _write_ready_phase10_sources()
    report = persist_phase11_live_canary_preparation_blocked_design_report(run_phase10_first=False)

    assert report["status"] == STATUS_PHASE11_LIVE_CANARY_PREPARATION_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase11_live_canary_preparation_blocked_design_report.json").exists()
    assert Path("storage/latest/phase11_live_canary_preparation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase11_live_canary_preparation_validation_report.json").exists()
    assert Path("storage/latest/phase11_live_canary_preparation_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE11_LIVE_CANARY_PREPARATION_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()
    assert Path("storage/live_canary/phase11_live_canary_preparation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase11_live_canary_preparation_registry_record.json").exists()
