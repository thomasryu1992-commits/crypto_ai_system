from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    PHASE7_15_OPERATOR_DECISION_PENDING,
    PHASE7_15_OPERATOR_SIGNATURE_PLACEHOLDER,
    PHASE7_15_APPROVAL_SCOPE,
    build_phase7_15_operator_decision_intake_template_report,
    build_phase7_15_negative_fixtures,
    persist_phase7_15_operator_decision_intake_template_report,
    scan_phase7_15_package_boundary,
    validate_operator_decision_intake_template,
    validate_phase7_15_negative_fixtures,
)
from tests.agents.test_phase7_15_operator_decision_intake_template import _write_ready_phase7_14_sources


def test_phase7_15_template_has_revised_boundary_fields() -> None:
    _write_ready_phase7_14_sources()
    report, template, _guard = build_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)

    assert report["status"] == "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_RECORDED_REVIEW_ONLY"
    assert template["phase"] == "7.15"
    assert template["source_phase"] == "7.14"
    assert template["template_id"] == template["operator_decision_intake_id"]
    assert template["source_phase7_14_packet_id"] == "phase7_14_ready_review"
    assert template["source_phase7_14_packet_hash"] == "phase7_14_hash_fixture"
    assert template["source_ref"]["source_phase7_14_packet_id"] == template["source_phase7_14_packet_id"]
    assert template["source_ref"]["source_phase7_14_packet_hash"] == template["source_phase7_14_packet_hash"]
    assert template["source_hash"] == template["source_phase7_14_packet_hash"]
    assert template["derived_template_hash"] == template["operator_decision_intake_template_sha256"]
    assert template["operator_decision"] == PHASE7_15_OPERATOR_DECISION_PENDING
    assert template["risk_ack"]["operator_acknowledgement_required"] is True
    assert template["execution_disabled_ack"] is True
    assert template["approval_scope"] == PHASE7_15_APPROVAL_SCOPE
    assert template["operator_signature_placeholder"] == PHASE7_15_OPERATOR_SIGNATURE_PLACEHOLDER
    assert "approval_intake_id" not in template
    assert report["phase7_14_to_7_15_lineage_preserved"] is True
    assert report["operator_decision_intake_registry_separate_from_approval_intake"] is True
    assert report["approval_intake_validator_reused"] is False


def test_phase7_15_negative_fixtures_block_fail_closed() -> None:
    _write_ready_phase7_14_sources()
    _report, template, _guard = build_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)
    fixtures = build_phase7_15_negative_fixtures(template)
    assert sorted(fixtures) == sorted(
        [
            "missing_source_hash.json",
            "mismatched_source_packet_id.json",
            "unsafe_execution_flag_true.json",
            "missing_operator_acknowledgement.json",
            "stale_decision_timestamp.json",
            "missing_execution_disabled_ack.json",
            "missing_operator_signature_placeholder.json",
            "approval_intake_misused_as_operator_decision_intake.json",
        ]
    )
    results = validate_phase7_15_negative_fixtures(template)
    assert results["all_negative_fixtures_blocked"] is True
    for result in results["results"].values():
        assert result["blocked"] is True
        assert result["fail_closed"] is True
        assert result["block_reasons"]


def test_phase7_15_package_boundary_scan_blocks_forbidden_artifacts(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed_phase7_15_package"
    allowed_root.mkdir()
    (allowed_root / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json").write_text("{}", encoding="utf-8")
    allowed_scan = scan_phase7_15_package_boundary(allowed_root)
    assert allowed_scan["blocked"] is False
    assert allowed_scan["forbidden_artifacts_found"] == []

    forbidden_root = tmp_path / "forbidden_phase7_15_package"
    forbidden_root.mkdir()
    (forbidden_root / "signed_testnet_order_executor.py").write_text("# forbidden", encoding="utf-8")
    forbidden_scan = scan_phase7_15_package_boundary(forbidden_root)
    assert forbidden_scan["blocked"] is True
    assert forbidden_scan["fail_closed"] is True
    assert "signed_testnet_order_executor.py" in forbidden_scan["forbidden_artifacts_found"]


def test_phase7_15_persist_writes_revised_boundary_artifacts() -> None:
    _write_ready_phase7_14_sources()
    report = persist_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)
    phase_dir = Path("storage/phase7_15_operator_decision_intake_template")

    assert report["status"] == "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_RECORDED_REVIEW_ONLY"
    for rel in [
        "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json",
        "operator_decision_intake_template_guard_report.json",
        "operator_decision_intake_template_registry.jsonl",
        "phase7_15_operator_decision_intake_handoff.md",
        "phase7_15_operator_decision_intake_template_validation_report.json",
        "negative_fixture_results.json",
        "phase7_15_package_boundary_scan.json",
    ]:
        assert (phase_dir / rel).exists(), rel
    for rel in [
        "missing_source_hash.json",
        "mismatched_source_packet_id.json",
        "unsafe_execution_flag_true.json",
        "missing_operator_acknowledgement.json",
        "stale_decision_timestamp.json",
        "missing_execution_disabled_ack.json",
        "missing_operator_signature_placeholder.json",
        "approval_intake_misused_as_operator_decision_intake.json",
    ]:
        assert (phase_dir / "negative_fixtures" / rel).exists(), rel

    template = json.loads((phase_dir / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json").read_text(encoding="utf-8"))
    validation = json.loads((phase_dir / "phase7_15_operator_decision_intake_template_validation_report.json").read_text(encoding="utf-8"))
    scan = json.loads((phase_dir / "phase7_15_package_boundary_scan.json").read_text(encoding="utf-8"))
    registry_line = (phase_dir / "operator_decision_intake_template_registry.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    registry = json.loads(registry_line)

    assert validation["passed_review_only"] is True
    assert validation["approval_intake_validator_reused"] is False
    assert scan["blocked"] is False
    assert registry["operator_decision_intake_registry_id"]
    assert registry["source_phase7_14_packet_id"] == template["source_phase7_14_packet_id"]
    assert registry["source_phase7_14_packet_hash"] == template["source_phase7_14_packet_hash"]
    assert registry["derived_template_hash"] == template["derived_template_hash"]
    assert registry["ready_for_signed_testnet_execution"] is False
    assert registry["testnet_order_submission_allowed"] is False
    assert registry["signed_order_executor_enabled"] is False


def test_phase7_15_validator_blocks_approval_intake_misuse() -> None:
    _write_ready_phase7_14_sources()
    _report, template, _guard = build_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)
    template["approval_intake_id"] = template["operator_decision_intake_id"]
    template["validator_name"] = "approval_intake_validator"
    result = validate_operator_decision_intake_template(template)
    assert result["template_valid_review_only"] is False
    assert result["template_blocked_fail_closed"] is True
    assert "APPROVAL_INTAKE_ID_MISUSED_AS_OPERATOR_DECISION_INTAKE_ID" in result["template_blockers"]
    assert "APPROVAL_INTAKE_VALIDATOR_MISUSED_FOR_OPERATOR_DECISION_INTAKE" in result["template_blockers"]
