from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase8_4_signed_testnet_executor_final_guard import (
    persist_phase8_4_signed_testnet_executor_final_guard_report,
)
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase9_1_single_signed_testnet_enablement_intake_report,
    persist_phase9_1_single_signed_testnet_enablement_intake_report,
    validate_phase9_1_single_signed_testnet_enablement_intake,
)
from tests.agents.test_phase8_4_signed_testnet_executor_final_guard import _write_ready_phase8_3_sources


def _write_ready_phase8_4_sources() -> None:
    _write_ready_phase8_3_sources()
    cfg = load_config()
    persist_phase8_4_signed_testnet_executor_final_guard_report(cfg=cfg, run_phase8_3_first=False)


def test_phase9_1_builds_single_order_intake_template_still_disabled() -> None:
    _write_ready_phase8_4_sources()
    cfg = load_config()
    report, intake, guard_report, negative_fixture_results = build_phase9_1_single_signed_testnet_enablement_intake_report(
        cfg=cfg,
        run_phase8_4_first=False,
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase9_1_single_signed_testnet_enablement_intake_ready"] is True
    assert report["phase9_1_actual_enablement_approval_complete"] is False
    assert report["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert intake["intake_type"] == "phase9_1_single_signed_testnet_enablement_intake_review_only"
    assert intake["review_only"] is True
    assert intake["single_order_scope"] is True
    assert intake["max_order_count"] == 1
    assert float(intake["small_max_notional"]) <= 10.0
    assert float(intake["daily_loss_cap"]) <= 15.0
    assert intake["testnet_only_key_fingerprint_required"] is True
    assert intake["fresh_preorder_risk_gate_evidence_present"] is True
    assert intake["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert guard_report["guard_passed"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, intake, guard_report):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["order_endpoint_called"] is False
        assert payload["http_request_sent"] is False
        assert payload["signature_created"] is False
        assert payload["actual_order_submission_performed"] is False


def test_phase9_1_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase8_4_sources()
    report = persist_phase9_1_single_signed_testnet_enablement_intake_report(run_phase8_4_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase9_1_single_signed_testnet_enablement_intake_report.json").exists()
    assert Path("storage/latest/single_signed_testnet_enablement_intake_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/single_signed_testnet_enablement_intake_guard_report.json").exists()
    assert Path("storage/latest/phase9_1_negative_fixture_results.json").exists()
    assert Path("storage/signed_testnet/single_signed_testnet_enablement_intake_REVIEW_ONLY.json").exists()
    assert Path("storage/phase9_1_single_signed_testnet_enablement_intake/PHASE9_1_SINGLE_SIGNED_TESTNET_ENABLEMENT_INTAKE_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase9_1_validator_blocks_over_scope_and_execution_flags() -> None:
    _write_ready_phase8_4_sources()
    cfg = load_config()
    _report, intake, _guard_report, _fixtures = build_phase9_1_single_signed_testnet_enablement_intake_report(
        cfg=cfg,
        run_phase8_4_first=False,
    )
    intake["max_order_count"] = 2
    intake["small_max_notional"] = "1000.0"
    intake["phase9_2_single_testnet_order_submit_may_begin"] = True
    intake["testnet_order_submission_allowed"] = True
    intake["order_endpoint_called"] = True

    result = validate_phase9_1_single_signed_testnet_enablement_intake(intake)

    assert result["phase9_1_single_signed_testnet_enablement_intake_valid_review_only"] is False
    assert result["phase9_1_single_signed_testnet_enablement_intake_blocked_fail_closed"] is True
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]
    assert "phase9_2_single_testnet_order_submit_may_begin" in result["unsafe_truthy_fields"]
    blockers = result["phase9_1_intake_blockers"]
    assert "PHASE9_1_MAX_ORDER_COUNT_NOT_ONE" in blockers
    assert "PHASE9_1_SMALL_MAX_NOTIONAL_INVALID_OR_TOO_HIGH" in blockers
    assert any(item.startswith("UNSAFE_PHASE9_1_INTAKE_FLAGS:") for item in blockers)


def test_phase9_1_actual_approval_requires_signature_fingerprint_and_kill_switch() -> None:
    _write_ready_phase8_4_sources()
    cfg = load_config()
    _report, intake, _guard_report, _fixtures = build_phase9_1_single_signed_testnet_enablement_intake_report(
        cfg=cfg,
        run_phase8_4_first=False,
    )
    result = validate_phase9_1_single_signed_testnet_enablement_intake(intake, require_actual_operator_approval=True)

    assert result["phase9_1_single_signed_testnet_enablement_intake_valid_review_only"] is False
    blockers = result["phase9_1_actual_approval_blockers"]
    assert "PHASE9_1_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL" in blockers
    assert "PHASE9_1_OPERATOR_SIGNATURE_MISSING" in blockers
    assert "PHASE9_1_TESTNET_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER" in blockers
    assert "PHASE9_1_KILL_SWITCH_NOT_CONFIRMED_FOR_ACTUAL_APPROVAL" in blockers
    assert result["phase9_2_single_testnet_order_submit_may_begin"] is False


def test_phase9_1_blocks_if_phase8_4_not_ready() -> None:
    _write_ready_phase8_4_sources()
    path = Path("storage/latest/phase8_4_signed_testnet_executor_final_guard_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_BLOCKED_REVIEW_ONLY"
    source["blocked"] = True
    source["fail_closed"] = True
    source["phase9_1_single_signed_testnet_enablement_intake_may_begin"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _intake, _guard_report, _fixtures = build_phase9_1_single_signed_testnet_enablement_intake_report(
        cfg=cfg,
        run_phase8_4_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE9_1_REQUIRED_EVIDENCE_NOT_READY:phase8_4_report" in report["block_reasons"]
    assert report["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False
