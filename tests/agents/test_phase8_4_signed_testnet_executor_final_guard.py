from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase8_4_signed_testnet_executor_final_guard import (
    REQUIRED_FINAL_GUARD_CHECKS,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase8_4_signed_testnet_executor_final_guard_report,
    persist_phase8_4_signed_testnet_executor_final_guard_report,
    validate_signed_testnet_executor_final_guard,
)
from tests.agents.test_phase8_3_hot_path_preorder_risk_gate import _write_ready_phase8_2_sources
from crypto_ai_system.validation.phase8_3_hot_path_preorder_risk_gate import persist_phase8_3_hot_path_preorder_risk_gate_report


def _write_ready_phase8_3_sources() -> None:
    _write_ready_phase8_2_sources()
    cfg = load_config()
    persist_phase8_3_hot_path_preorder_risk_gate_report(cfg=cfg, run_phase8_2_first=False)


def test_phase8_4_builds_final_guard_still_disabled() -> None:
    _write_ready_phase8_3_sources()
    cfg = load_config()
    report, final_guard, guard_report, still_disabled_flags = build_phase8_4_signed_testnet_executor_final_guard_report(
        cfg=cfg,
        run_phase8_3_first=False,
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase8_4_signed_testnet_executor_final_guard_ready"] is True
    assert report["phase9_1_single_signed_testnet_enablement_intake_may_begin"] is True
    assert final_guard["guard_type"] == "phase8_4_signed_testnet_executor_final_guard_review_only"
    assert final_guard["review_only"] is True
    assert final_guard["final_guard_only"] is True
    assert final_guard["still_disabled"] is True
    assert final_guard["phase8_4_passes_for_phase9_intake_preparation_only"] is True
    assert final_guard["phase9_order_submission_not_authorized_by_phase8_4"] is True
    assert final_guard["required_final_guard_checks"] == REQUIRED_FINAL_GUARD_CHECKS
    assert all(final_guard["check_results"][check] is True for check in REQUIRED_FINAL_GUARD_CHECKS)
    assert guard_report["guard_passed"] is True
    assert still_disabled_flags["signed_order_executor_enabled"] is False
    for payload in (report, final_guard, guard_report, still_disabled_flags):
        assert payload["ready_for_signed_testnet_execution"] is False
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["actual_order_submission_performed"] is False
        assert payload["order_endpoint_called"] is False
        assert payload["http_request_sent"] is False
        assert payload["signature_created"] is False


def test_phase8_4_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase8_3_sources()
    report = persist_phase8_4_signed_testnet_executor_final_guard_report(run_phase8_3_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase8_4_signed_testnet_executor_final_guard_report.json").exists()
    assert Path("storage/latest/signed_testnet_executor_final_guard_review_only.json").exists()
    assert Path("storage/latest/signed_testnet_executor_final_guard_guard_report.json").exists()
    assert Path("storage/latest/still_disabled_executor_enablement_flags.json").exists()
    assert Path("storage/signed_testnet/signed_testnet_executor_final_guard_review_only.json").exists()
    assert Path("storage/phase8_4_signed_testnet_executor_final_guard/PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase8_4_validator_blocks_executor_enablement_and_order_submission_flags() -> None:
    _write_ready_phase8_3_sources()
    cfg = load_config()
    _report, final_guard, _guard_report, _flags = build_phase8_4_signed_testnet_executor_final_guard_report(
        cfg=cfg,
        run_phase8_3_first=False,
    )
    final_guard["signed_order_executor_enabled"] = True
    final_guard["testnet_order_submission_allowed"] = True
    final_guard["order_endpoint_called"] = True
    final_guard["signature_created"] = True
    final_guard["check_results"]["executor_enablement_flags_still_disabled"] = False

    result = validate_signed_testnet_executor_final_guard(final_guard)

    assert result["signed_testnet_executor_final_guard_valid_review_only"] is False
    assert result["signed_testnet_executor_final_guard_blocked_fail_closed"] is True
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    blockers = result["signed_testnet_executor_final_guard_blockers"]
    assert any(item.startswith("UNSAFE_PHASE8_4_FINAL_GUARD_FLAGS:") for item in blockers)
    assert "PHASE8_4_FINAL_GUARD_CHECKS_NOT_TRUE:executor_enablement_flags_still_disabled" in blockers


def test_phase8_4_blocks_if_phase8_3_not_ready() -> None:
    _write_ready_phase8_3_sources()
    path = Path("storage/latest/phase8_3_hot_path_preorder_risk_gate_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE8_3_HOT_PATH_PREORDER_RISK_GATE_BLOCKED_REVIEW_ONLY"
    source["blocked"] = True
    source["fail_closed"] = True
    source["phase8_3_hot_path_risk_gate_ready"] = False
    source["phase8_4_final_guard_may_begin"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _final_guard, _guard_report, _flags = build_phase8_4_signed_testnet_executor_final_guard_report(
        cfg=cfg,
        run_phase8_3_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE8_4_REQUIRED_EVIDENCE_NOT_READY:phase8_3_report" in report["block_reasons"]
    assert report["phase9_1_single_signed_testnet_enablement_intake_may_begin"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase8_4_blocks_source_unsafe_secret_and_http_flags() -> None:
    _write_ready_phase8_3_sources()
    secret_path = Path("storage/latest/secret_manager_key_handling_design_review_only.json")
    secret = json.load(open(secret_path, encoding="utf-8"))
    secret["secret_value_accessed"] = True
    secret_path.write_text(json.dumps(secret, ensure_ascii=False, indent=2), encoding="utf-8")
    dry_path = Path("storage/latest/exchange_adapter_write_path_dry_validation_review_only.json")
    dry = json.load(open(dry_path, encoding="utf-8"))
    dry["http_request_sent"] = True
    dry_path.write_text(json.dumps(dry, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _final_guard, _guard_report, _flags = build_phase8_4_signed_testnet_executor_final_guard_report(
        cfg=cfg,
        run_phase8_3_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert "secret_key_design" in report["unsafe_flags_by_artifact"]
    assert "write_path_dry_validation" in report["unsafe_flags_by_artifact"]
    assert "secret_value_accessed" in report["unsafe_flags_by_artifact"]["secret_key_design"]
    assert "http_request_sent" in report["unsafe_flags_by_artifact"]["write_path_dry_validation"]
    assert report["actual_order_submission_performed"] is False
    assert report["signed_order_executor_enabled"] is False
