from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from tests.agents.test_phase7_15_operator_decision_intake_template import _write_ready_phase7_14_sources
from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    build_phase7_15_operator_decision_intake_template_report,
)
from crypto_ai_system.validation.phase7_16_operator_decision_intake_validator import (
    build_phase7_16_operator_decision_intake_validator_report,
)
from crypto_ai_system.validation.phase7_17_final_pre_executor_review_packet import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_17_final_pre_executor_review_packet_report,
    persist_phase7_17_final_pre_executor_review_packet_report,
    validate_final_pre_executor_review_packet,
)


def _write_ready_phase7_16_sources() -> None:
    _write_ready_phase7_14_sources()
    cfg = load_config()
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    phase7_15_report, template, template_guard = build_phase7_15_operator_decision_intake_template_report(
        cfg=cfg, run_phase7_14_first=False
    )
    atomic_write_json(latest / "phase7_15_operator_decision_intake_template_report.json", phase7_15_report)
    atomic_write_json(latest / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(latest / "operator_decision_intake_template_guard_report.json", template_guard)
    phase7_16_report, submission, validation_report = build_phase7_16_operator_decision_intake_validator_report(
        cfg=cfg, run_phase7_15_first=False
    )
    atomic_write_json(latest / "phase7_16_operator_decision_intake_validator_report.json", phase7_16_report)
    atomic_write_json(latest / "operator_decision_intake_valid_submission_FIXTURE_REVIEW_ONLY.json", submission)
    atomic_write_json(latest / "operator_decision_intake_validation_report_review_only.json", validation_report)


def test_phase7_17_builds_final_pre_executor_review_packet_still_disabled() -> None:
    _write_ready_phase7_16_sources()
    cfg = load_config()
    report, packet, guard = build_phase7_17_final_pre_executor_review_packet_report(cfg=cfg, run_phase7_16_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_final_pre_executor_review_ready"] is True
    assert report["phase7_review_chain_complete"] is True
    assert report["phase8_preparation_review_may_begin"] is True
    assert packet["packet_type"] == "phase7_17_final_pre_executor_review_packet_review_only"
    assert packet["review_only"] is True
    assert packet["final_pre_executor_review_only"] is True
    assert packet["not_runtime_authority"] is True
    assert guard["guard_passed"] is True
    assert report["actual_phase8_approval_granted"] is False
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase7_17_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase7_16_sources()
    report = persist_phase7_17_final_pre_executor_review_packet_report(run_phase7_16_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase7_17_final_pre_executor_review_packet_report.json").exists()
    assert Path("storage/latest/phase7_final_pre_executor_review_packet_review_only.json").exists()
    assert Path("storage/latest/phase7_final_pre_executor_review_guard_report.json").exists()
    assert Path("storage/signed_testnet/phase7_final_pre_executor_review_packet_review_only.json").exists()


def test_phase7_17_packet_validator_blocks_execution_flags() -> None:
    _write_ready_phase7_16_sources()
    cfg = load_config()
    _report, packet, _guard = build_phase7_17_final_pre_executor_review_packet_report(cfg=cfg, run_phase7_16_first=False)
    packet["ready_for_signed_testnet_execution"] = True
    packet["signed_order_executor_enabled"] = True

    result = validate_final_pre_executor_review_packet(packet)

    assert result["final_packet_valid_review_only"] is False
    assert result["final_packet_blocked_fail_closed"] is True
    assert "ready_for_signed_testnet_execution" in result["unsafe_truthy_fields"]
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]


def test_phase7_17_blocks_if_phase7_16_not_ready() -> None:
    _write_ready_phase7_16_sources()
    path = Path("storage/latest/phase7_16_operator_decision_intake_validator_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_BLOCKED_REVIEW_ONLY"
    source["phase7_16_intake_validation_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_17_final_pre_executor_review_packet_report(cfg=cfg, run_phase7_16_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_17_REQUIRED_EVIDENCE_NOT_READY:operator_decision_intake_validator" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False
