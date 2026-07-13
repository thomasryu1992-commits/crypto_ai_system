from __future__ import annotations

from pathlib import Path

from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import persist_phase6_2_operator_unlock_request_fixture_validator_report
from crypto_ai_system.validation.phase6_3_signed_testnet_readiness_gate_review import (
    STATUS_BLOCKED_REVIEW_ONLY,
    build_phase6_3_signed_testnet_readiness_gate_review_report,
    persist_phase6_3_signed_testnet_readiness_gate_review_report,
)


def _prepare_prerequisites() -> None:
    persist_phase5_manual_approval_intake_validation_report()
    persist_phase5_1_manual_approval_operator_handoff_report()
    persist_phase5_2_manual_approval_submission_fixture_validator_report()
    persist_phase6_signed_testnet_preparation_preview_report()
    persist_phase6_1_signed_testnet_operator_unlock_request_template_report()
    persist_phase6_2_operator_unlock_request_fixture_validator_report()


def test_phase6_3_signed_testnet_readiness_gate_blocks_without_actual_approval_or_unlock() -> None:
    _prepare_prerequisites()
    report = build_phase6_3_signed_testnet_readiness_gate_review_report()

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["actual_manual_approval_submission_present"] is False
    assert report["actual_operator_unlock_request_present"] is False
    assert report["approval_intake_validated"] is False
    assert report["operator_unlock_request_validated"] is False
    assert report["signed_testnet_readiness_passed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert "ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING" in report["readiness_blockers"]
    assert "ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING" in report["readiness_blockers"]
    assert "APPROVAL_INTAKE_NOT_VALIDATED" in report["readiness_blockers"]


def test_phase6_3_persists_latest_report_and_registry_record() -> None:
    _prepare_prerequisites()
    report = persist_phase6_3_signed_testnet_readiness_gate_review_report()
    root = Path.cwd()

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert (root / "storage/latest/phase6_3_signed_testnet_readiness_gate_review_report.json").exists()
    assert (root / "storage/latest/phase6_3_signed_testnet_readiness_gate_review_registry_record.json").exists()
    assert (root / "storage/registries/phase6_3_signed_testnet_readiness_gate_review_registry.jsonl").exists()
    assert not (root / "storage/latest/operator_unlock_request.json").exists()
    assert not (root / "storage/signed_testnet/operator_unlock_request.json").exists()
