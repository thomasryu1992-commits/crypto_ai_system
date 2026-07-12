from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase10_signed_testnet_session_validation_blocked_design import (
    SESSION_METRICS_REQUIRED,
    SESSION_SCENARIOS_REQUIRED,
    STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY,
    build_phase10_signed_testnet_session_validation_blocked_design_report,
    persist_phase10_signed_testnet_session_validation_blocked_design_report,
    validate_phase10_signed_testnet_session_validation_design,
)
from tests.agents.test_phase9_3_9_4_blocked_design_hardening import _write_ready_phase9_3_sources


def _write_ready_phase9_4_sources() -> None:
    _write_ready_phase9_3_sources()
    from crypto_ai_system.validation.phase9_3_9_4_blocked_design_hardening import (
        persist_phase9_3_9_4_blocked_design_hardening_report,
    )

    persist_phase9_3_9_4_blocked_design_hardening_report(run_phase9_3_first=False)


def test_phase10_signed_testnet_session_validation_design_records_blocked_artifacts() -> None:
    _write_ready_phase9_4_sources()
    cfg = load_config()
    report, design, validation, negative_fixture_results = build_phase10_signed_testnet_session_validation_blocked_design_report(
        cfg=cfg,
        run_phase9_3_9_4_first=False,
    )

    assert report["status"] == STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase10_signed_testnet_session_validation_design_recorded"] is True
    assert report["phase10_signed_testnet_session_validation_may_begin"] is False
    assert report["phase10_session_validation_started"] is False
    assert report["phase10_promotion_review_packet_created"] is False
    assert report["live_canary_preparation_may_begin"] is False
    assert "PHASE10_BLOCKED_UNTIL_REAL_PHASE9_4_RECONCILIATION_AND_MULTIPLE_TESTNET_SESSIONS_EXIST" in report["block_reasons"]
    assert validation["phase10_signed_testnet_session_validation_design_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for scenario in SESSION_SCENARIOS_REQUIRED:
        assert scenario in design["required_session_scenarios"]
        assert scenario in design["session_validation_plan"]
    for metric in SESSION_METRICS_REQUIRED:
        assert metric in design["required_session_metrics"]
        assert metric in design["metric_collection_plan"]


def test_phase10_validator_blocks_promotion_or_live_canary_activation() -> None:
    _write_ready_phase9_4_sources()
    cfg = load_config()
    _report, design, _validation, _negative_fixture_results = build_phase10_signed_testnet_session_validation_blocked_design_report(
        cfg=cfg,
        run_phase9_3_9_4_first=False,
    )
    design["phase10_signed_testnet_session_validation_may_begin"] = True
    design["phase10_session_validation_started"] = True
    design["phase10_promotion_review_packet_created"] = True
    design["live_canary_preparation_may_begin"] = True

    result = validate_phase10_signed_testnet_session_validation_design(design)

    assert result["phase10_signed_testnet_session_validation_design_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE10_SESSION_VALIDATION_UNSAFE_FIELD:phase10_signed_testnet_session_validation_may_begin" in result["block_reasons"]
    assert "PHASE10_SESSION_VALIDATION_UNSAFE_FIELD:live_canary_preparation_may_begin" in result["block_reasons"]
    assert "phase10_signed_testnet_session_validation_may_begin" in result["unsafe_truthy_fields"]


def test_phase10_validator_requires_all_scenarios_and_metrics() -> None:
    _write_ready_phase9_4_sources()
    cfg = load_config()
    _report, design, _validation, _negative_fixture_results = build_phase10_signed_testnet_session_validation_blocked_design_report(
        cfg=cfg,
        run_phase9_3_9_4_first=False,
    )
    design["required_session_scenarios"] = [s for s in SESSION_SCENARIOS_REQUIRED if s != "partial_fill_case"]
    design["required_session_metrics"] = [m for m in SESSION_METRICS_REQUIRED if m != "paper_testnet_gap"]
    metric_plan = dict(design["metric_collection_plan"])
    metric_plan.pop("paper_testnet_gap")
    design["metric_collection_plan"] = metric_plan

    result = validate_phase10_signed_testnet_session_validation_design(design)

    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE10_SESSION_SCENARIO_MISSING:partial_fill_case" in result["block_reasons"]
    assert "PHASE10_SESSION_METRIC_MISSING:paper_testnet_gap" in result["block_reasons"]
    assert "PHASE10_SESSION_METRIC_PLAN_MISSING:paper_testnet_gap" in result["block_reasons"]


def test_phase10_persist_writes_latest_signed_testnet_and_registry_artifacts() -> None:
    _write_ready_phase9_4_sources()
    report = persist_phase10_signed_testnet_session_validation_blocked_design_report(run_phase9_3_9_4_first=False)

    assert report["status"] == STATUS_PHASE10_SESSION_VALIDATION_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase10_signed_testnet_session_validation_blocked_design_report.json").exists()
    assert Path("storage/latest/phase10_signed_testnet_session_validation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase10_signed_testnet_session_validation_validation_report.json").exists()
    assert Path("storage/latest/phase10_signed_testnet_session_validation_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE10_SIGNED_TESTNET_SESSION_VALIDATION_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase10_signed_testnet_session_validation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
