from __future__ import annotations

from pathlib import Path

from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import persist_phase6_2_operator_unlock_request_fixture_validator_report
from crypto_ai_system.validation.phase6_3_signed_testnet_readiness_gate_review import persist_phase6_3_signed_testnet_readiness_gate_review_report
from crypto_ai_system.validation.phase6_4_signed_testnet_readiness_review_packet import (
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase6_4_signed_testnet_readiness_review_packet_report,
    persist_phase6_4_signed_testnet_readiness_review_packet_report,
)


def _prepare_prerequisites() -> None:
    persist_phase5_manual_approval_intake_validation_report()
    persist_phase5_1_manual_approval_operator_handoff_report()
    persist_phase5_2_manual_approval_submission_fixture_validator_report()
    persist_phase6_signed_testnet_preparation_preview_report()
    persist_phase6_1_signed_testnet_operator_unlock_request_template_report()
    persist_phase6_2_operator_unlock_request_fixture_validator_report()
    persist_phase6_3_signed_testnet_readiness_gate_review_report()


def test_phase6_4_builds_operator_decision_handoff_packet_without_unlocking() -> None:
    _prepare_prerequisites()
    report = build_phase6_4_signed_testnet_readiness_review_packet_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["operator_decision_handoff_created"] is True
    assert report["signed_testnet_readiness_status"] == "SIGNED_TESTNET_READINESS_BLOCKED_REVIEW_ONLY"
    assert report["actual_manual_approval_submission_present"] is False
    assert report["actual_operator_unlock_request_present"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert "ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING" in report["readiness_blockers"]
    assert "ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING" in report["readiness_blockers"]
    assert report["operator_decision_checklist"]
    assert all(item["required_before_signed_testnet"] is True for item in report["operator_decision_checklist"])


def test_phase6_4_persists_review_packet_handoff_and_registry_record() -> None:
    _prepare_prerequisites()
    report = persist_phase6_4_signed_testnet_readiness_review_packet_report()
    root = Path.cwd()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert (root / "storage/latest/phase6_4_signed_testnet_readiness_review_packet_report.json").exists()
    assert (root / "storage/latest/signed_testnet_readiness_review_packet.json").exists()
    assert (root / "storage/latest/SIGNED_TESTNET_OPERATOR_DECISION_HANDOFF_REVIEW_ONLY.md").exists()
    assert (root / "storage/latest/phase6_4_signed_testnet_readiness_review_packet_registry_record.json").exists()
    assert (root / "storage/registries/phase6_4_signed_testnet_readiness_review_packet_registry.jsonl").exists()
    assert not (root / "storage/latest/operator_unlock_request.json").exists()
    assert not (root / "storage/signed_testnet/operator_unlock_request.json").exists()
