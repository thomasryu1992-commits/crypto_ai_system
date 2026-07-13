from __future__ import annotations

import re
import sys
import tomllib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

EXPECTED_STEP = "P70"
EXPECTED_PROJECT_VERSION = "p70_venue_neutral_execution_contract"
EXPECTED_PYPROJECT_VERSION = "0.286.2"
DISABLED_WORDING = [
    "Live order execution: disabled",
    "Signed testnet execution: disabled",
    "Ready for signed testnet execution: false",
    "Testnet order submission: disabled",
    "External order submission: disabled",
    "Place order: disabled",
    "Cancel order: disabled",
    "Signed order executor: disabled",
    "API key value access: disabled",
    "Settings score-weight mutation: disabled",
]
SOURCE_EXCLUDED_PREFIXES = {"storage", "data/reports", "data/stores", "dist"}
VALIDATION_INCLUDED_PREFIXES = {"storage/latest", "storage/logs", "data/reports", "data/stores"}

AGENT_LIBRARY_WORKFLOW_COMMANDS = [
    "python scripts/lint_agents.py",
    "python scripts/validate_agent_contracts.py",
    "python scripts/validate_agent_outputs.py",
    "python scripts/run_agent_evals.py",
    "python scripts/generate_agent_index.py",
    "python scripts/build_agent_library_contract_review.py",
    "python scripts/build_review_only_export_packet.py",
    "python scripts/build_canary_outcome_report.py",
    "python scripts/build_live_scaled_readiness_gate.py",
    "python scripts/build_baseline_integrity_freeze.py",
    "python scripts/build_valid_price_lineage_artifacts.py",
    "python scripts/build_paper_data_quality_gate.py",
    "python scripts/build_paper_strategy_validation.py",
    "python scripts/build_phase4_outcome_candidate_feedback.py",
    "python scripts/build_phase4_1_paper_outcome_sample_accumulation.py",
    "python scripts/build_phase4_2_signal_drift_candidate_readiness.py",
    "python scripts/build_phase4_3_research_signal_score_bucket_replay.py",
    "python scripts/build_phase4_4_candidate_profile_review_packet.py",
    "python scripts/build_phase5_manual_approval_intake_validation.py",
    "python scripts/build_phase5_1_manual_approval_operator_handoff.py",
    "python scripts/build_phase5_2_manual_approval_submission_fixture_validator.py",
    "python scripts/build_phase6_signed_testnet_preparation_preview.py",
    "python scripts/build_phase6_1_signed_testnet_operator_unlock_request_template.py",
    "python scripts/build_phase6_2_operator_unlock_request_fixture_validator.py",
    "python scripts/build_phase6_3_signed_testnet_readiness_gate_review.py",
    "python scripts/build_phase6_4_signed_testnet_readiness_review_packet.py",
    "python scripts/build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py",
    "python scripts/build_phase6_6_actual_intake_validation_bridge.py",
    "python scripts/build_phase7_signed_testnet_validation_design_guard.py",
    "python scripts/build_phase7_1_signed_testnet_pre_submit_payload_guard.py",
    "python scripts/run_phase7_1_review_chain.py",
    "python scripts/build_phase7_1_1_review_chain_state_doctor.py",
    "python scripts/build_phase7_2_executor_enablement_review_packet.py",
    "python scripts/build_phase7_3_disabled_signed_testnet_executor_review.py",
    "python scripts/build_phase7_4_disabled_execution_reconciliation_session_close.py",
    "python scripts/build_phase7_5_reconciliation_session_close_review_packet.py",
    "python scripts/build_phase7_6_disabled_signed_testnet_session_operator_handoff.py",
    "python scripts/build_phase7_7_future_executor_review_prerequisite_design.py",
    "python scripts/build_phase7_8_future_executor_approval_packet_template.py",
    "python scripts/build_phase7_9_future_executor_approval_intake_validator.py",
    "python scripts/build_phase7_10_future_executor_approval_review_packet.py",
    "python scripts/build_phase7_11_future_executor_enablement_design_review.py",
    "python scripts/build_phase7_12_future_executor_enablement_guard_fixture.py",
    "python scripts/build_phase7_13_future_executor_enablement_review_packet.py",
    "python scripts/build_phase7_14_future_executor_operator_decision_packet.py",
    "python -m pytest -q tests/agents/",
]
AGENT_LIBRARY_REQUIRED_PATHS = [
    "agents/README.md",
    "agent_contracts/permissions/read_only.yaml",
    "agent_contracts/permissions/paper_only.yaml",
    "agent_contracts/permissions/approval_required.yaml",
    "agent_contracts/permissions/prohibited_actions.yaml",
    "agent_contracts/schemas/agent_output.schema.json",
    "scripts/lint_agents.py",
    "scripts/validate_agent_contracts.py",
    "scripts/validate_agent_outputs.py",
    "scripts/run_agent_evals.py",
    "scripts/generate_agent_index.py",
    "scripts/build_agent_library_contract_review.py",
    "scripts/build_review_only_export_packet.py",
    "scripts/build_canary_outcome_report.py",
    "scripts/build_live_scaled_readiness_gate.py",
    "scripts/build_baseline_integrity_freeze.py",
    "src/crypto_ai_system/validation/baseline_integrity_freeze.py",
    "src/crypto_ai_system/validation/valid_price_lineage_artifacts.py",
    "scripts/build_valid_price_lineage_artifacts.py",
    "src/crypto_ai_system/validation/paper_strategy_validation.py",
    "scripts/build_paper_strategy_validation.py",
    "tests/agents/test_phase3_paper_strategy_validation.py",
    "src/crypto_ai_system/validation/phase4_outcome_candidate_feedback.py",
    "scripts/build_phase4_outcome_candidate_feedback.py",
    "tests/agents/test_phase4_outcome_candidate_feedback.py",
    "PHASE4_OUTCOME_CANDIDATE_FEEDBACK_REPORT.md",
    "src/crypto_ai_system/validation/phase4_1_paper_outcome_sample_accumulation.py",
    "scripts/build_phase4_1_paper_outcome_sample_accumulation.py",
    "tests/agents/test_phase4_1_paper_outcome_sample_accumulation.py",
    "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_REPORT.md",
    "src/crypto_ai_system/validation/phase4_2_signal_drift_candidate_readiness.py",
    "scripts/build_phase4_2_signal_drift_candidate_readiness.py",
    "tests/agents/test_phase4_2_signal_drift_candidate_readiness.py",
    "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_REPORT.md",
    "src/crypto_ai_system/validation/phase4_3_research_signal_score_bucket_replay.py",
    "scripts/build_phase4_3_research_signal_score_bucket_replay.py",
    "tests/agents/test_phase4_3_research_signal_score_bucket_replay.py",
    "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_REPORT.md",
    "src/crypto_ai_system/validation/phase4_4_candidate_profile_review_packet.py",
    "scripts/build_phase4_4_candidate_profile_review_packet.py",
    "tests/agents/test_phase4_4_candidate_profile_review_packet.py",
    "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_REPORT.md",
    "src/crypto_ai_system/validation/phase5_manual_approval_intake_validation.py",
    "scripts/build_phase5_manual_approval_intake_validation.py",
    "tests/agents/test_phase5_manual_approval_intake_validation.py",
    "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_REPORT.md",
    "src/crypto_ai_system/validation/phase5_1_manual_approval_operator_handoff.py",
    "scripts/build_phase5_1_manual_approval_operator_handoff.py",
    "tests/agents/test_phase5_1_manual_approval_operator_handoff.py",
    "PHASE5_1_MANUAL_APPROVAL_OPERATOR_HANDOFF_REPORT.md",
    "src/crypto_ai_system/validation/phase5_2_manual_approval_submission_fixture_validator.py",
    "scripts/build_phase5_2_manual_approval_submission_fixture_validator.py",
    "tests/agents/test_phase5_2_manual_approval_submission_fixture_validator.py",
    "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_REPORT.md",
    "src/crypto_ai_system/validation/phase6_signed_testnet_preparation_preview.py",
    "scripts/build_phase6_signed_testnet_preparation_preview.py",
    "tests/agents/test_phase6_signed_testnet_preparation_preview.py",
    "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_REPORT.md",
    "src/crypto_ai_system/validation/phase6_1_signed_testnet_operator_unlock_request_template.py",
    "scripts/build_phase6_1_signed_testnet_operator_unlock_request_template.py",
    "tests/agents/test_phase6_1_signed_testnet_operator_unlock_request_template.py",
    "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_REQUEST_TEMPLATE_REPORT.md",
    "src/crypto_ai_system/validation/phase6_2_operator_unlock_request_fixture_validator.py",
    "scripts/build_phase6_2_operator_unlock_request_fixture_validator.py",
    "tests/agents/test_phase6_2_operator_unlock_request_fixture_validator.py",
    "PHASE6_2_OPERATOR_UNLOCK_REQUEST_FIXTURE_VALIDATOR_REPORT.md",
    "src/crypto_ai_system/validation/phase6_3_signed_testnet_readiness_gate_review.py",
    "scripts/build_phase6_3_signed_testnet_readiness_gate_review.py",
    "tests/agents/test_phase6_3_signed_testnet_readiness_gate_review.py",
    "PHASE6_3_SIGNED_TESTNET_READINESS_GATE_REVIEW_REPORT.md",
    "src/crypto_ai_system/validation/phase6_4_signed_testnet_readiness_review_packet.py",
    "scripts/build_phase6_4_signed_testnet_readiness_review_packet.py",
    "tests/agents/test_phase6_4_signed_testnet_readiness_review_packet.py",
    "PHASE6_4_SIGNED_TESTNET_READINESS_REVIEW_PACKET_REPORT.md",
    "src/crypto_ai_system/validation/phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py",
    "scripts/build_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py",
    "tests/agents/test_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox.py",
    "PHASE6_5_ACTUAL_MANUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_REPORT.md",
    "src/crypto_ai_system/validation/phase6_6_actual_intake_validation_bridge.py",
    "scripts/build_phase6_6_actual_intake_validation_bridge.py",
    "tests/agents/test_phase6_6_actual_intake_validation_bridge.py",
    "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_REPORT.md",
    "src/crypto_ai_system/validation/phase7_signed_testnet_validation_design_guard.py",
    "scripts/build_phase7_signed_testnet_validation_design_guard.py",
    "tests/agents/test_phase7_signed_testnet_validation_design_guard.py",
    "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_GUARD_REPORT.md",
    "src/crypto_ai_system/validation/phase7_1_signed_testnet_pre_submit_payload_guard.py",
    "scripts/build_phase7_1_signed_testnet_pre_submit_payload_guard.py",
    "tests/agents/test_phase7_1_signed_testnet_pre_submit_payload_guard.py",
    "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_REPORT.md",
    "src/crypto_ai_system/validation/review_chain_state_doctor.py",
    "scripts/run_phase7_1_review_chain.py",
    "scripts/build_phase7_1_1_review_chain_state_doctor.py",
    "tests/agents/test_phase7_1_1_review_chain_state_doctor.py",
    "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_REPORT.md",
    "src/crypto_ai_system/validation/phase7_2_executor_enablement_review_packet.py",
    "scripts/build_phase7_2_executor_enablement_review_packet.py",
    "tests/agents/test_phase7_2_executor_enablement_review_packet.py",
    "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_REPORT.md",
    "src/crypto_ai_system/execution/disabled_signed_testnet_executor.py",
    "src/crypto_ai_system/validation/phase7_3_disabled_signed_testnet_executor_review.py",
    "scripts/build_phase7_3_disabled_signed_testnet_executor_review.py",
    "tests/agents/test_phase7_3_disabled_signed_testnet_executor_review.py",
    "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_REVIEW_REPORT.md",
    "src/crypto_ai_system/validation/phase7_4_disabled_execution_reconciliation_session_close.py",
    "scripts/build_phase7_4_disabled_execution_reconciliation_session_close.py",
    "tests/agents/test_phase7_4_disabled_execution_reconciliation_session_close.py",
    "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_REPORT.md",
    "src/crypto_ai_system/validation/phase7_5_reconciliation_session_close_review_packet.py",
    "scripts/build_phase7_5_reconciliation_session_close_review_packet.py",
    "tests/agents/test_phase7_5_reconciliation_session_close_review_packet.py",
    "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_REPORT.md",
    "src/crypto_ai_system/validation/phase7_6_disabled_signed_testnet_session_operator_handoff.py",
    "scripts/build_phase7_6_disabled_signed_testnet_session_operator_handoff.py",
    "tests/agents/test_phase7_6_disabled_signed_testnet_session_operator_handoff.py",
    "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_REPORT.md",
    "src/crypto_ai_system/validation/phase7_7_future_executor_review_prerequisite_design.py",
    "scripts/build_phase7_7_future_executor_review_prerequisite_design.py",
    "tests/agents/test_phase7_7_future_executor_review_prerequisite_design.py",
    "src/crypto_ai_system/validation/phase7_8_future_executor_approval_packet_template.py",
    "scripts/build_phase7_8_future_executor_approval_packet_template.py",
    "tests/agents/test_phase7_8_future_executor_approval_packet_template.py",
    "src/crypto_ai_system/validation/phase7_9_future_executor_approval_intake_validator.py",
    "scripts/build_phase7_9_future_executor_approval_intake_validator.py",
    "tests/agents/test_phase7_9_future_executor_approval_intake_validator.py",
    "src/crypto_ai_system/validation/phase7_10_future_executor_approval_review_packet.py",
    "src/crypto_ai_system/validation/phase7_11_future_executor_enablement_design_review.py",
    "src/crypto_ai_system/validation/phase7_12_future_executor_enablement_guard_fixture.py",
    "src/crypto_ai_system/validation/phase7_13_future_executor_enablement_review_packet.py",
    "src/crypto_ai_system/validation/phase7_14_future_executor_operator_decision_packet.py",
    "scripts/build_phase7_10_future_executor_approval_review_packet.py",
    "scripts/build_phase7_11_future_executor_enablement_design_review.py",
    "scripts/build_phase7_12_future_executor_enablement_guard_fixture.py",
    "scripts/build_phase7_13_future_executor_enablement_review_packet.py",
    "scripts/build_phase7_14_future_executor_operator_decision_packet.py",
    "tests/agents/test_phase7_10_future_executor_approval_review_packet.py",
    "tests/agents/test_phase7_11_future_executor_enablement_design_review.py",
    "tests/agents/test_phase7_12_future_executor_enablement_guard_fixture.py",
    "tests/agents/test_phase7_13_future_executor_enablement_review_packet.py",
    "tests/agents/test_phase7_14_future_executor_operator_decision_packet.py",
    "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_REPORT.md",
    "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_REPORT.md",
    "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_REPORT.md",
    "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_REPORT.md",
    "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_REPORT.md",
    "tests/agents/test_phase1_baseline_integrity_freeze.py",
    "tests/agents/test_phase2_1_valid_price_lineage_artifacts.py",
    "PHASE2_1_VALID_PRICE_LINEAGE_ARTIFACTS_REPORT.md",
    "PHASE3_PAPER_STRATEGY_VALIDATION_REPORT.md",
    "PHASE1_BASELINE_INTEGRITY_FREEZE_REPORT.md",
    "tests/agents/test_step327_agent_library_ci_status_sync.py",
    "agents/risk/preorder_risk_gate_auditor.md",
    "agents/research/research_signal_builder.md",
    "agents/research/research_signal_qa_agent.md",
    "agents/research/signal_drift_detector.md",
    "agents/trading/trading_decision_reviewer.md",
    "agents/trading/price_structure_reviewer.md",
    "agents/trading/permission_boundary_auditor.md",
    "agents/execution/paper_execution_auditor.md",
    "agents/execution/reconciliation_auditor.md",
    "agents/execution/order_intent_chain_validator.md",
    "agents/feedback/outcome_feedback_analyst.md",
    "agents/feedback/performance_report_builder.md",
    "agents/feedback/candidate_profile_reviewer.md",
    "agents/qa/evidence_collector.md",
    "agents/qa/regression_runtime_hygiene_agent.md",
    "agents/approval/export_packet_agent.md",
    "tests/agents/test_step328_full_agent_role_expansion.py",
    "tests/agents/test_step328_preorder_risk_gate_auditor_completion.py",
]
AGENT_LIBRARY_DOC_WORDING = [
    "Step328 Full Agent Role Expansion",
    "Agent Library is a review-only contract layer",
    "Agent Library validation does not unlock signed testnet or live execution",
    "Current allowed stage: review-only / shadow / paper-preparation",
    "Phase 1 Baseline Integrity Freeze",
    "Phase 2 Paper Data Quality Hardening",
    "Phase 2.1 Valid Price Data & Lineage Artifact Generation",
    "Phase 3 Paper Strategy Validation",
    "Phase 4 Outcome Analytics & Candidate Profile",
    "Phase 4.1 Paper Outcome Sample Accumulation",
    "Phase 4.2 Signal Drift Review & Candidate Readiness Gate",
    "Phase 4.3 ResearchSignal Score Bucket & Drift Reduction Replay",
    "Phase 4.4 Candidate Profile Review Packet & Manual Approval Readiness",
    "Phase 5 Manual Approval Intake Validation",
    "Phase 5.1 Manual Approval Submission Template & Operator Handoff",
    "Phase 5.2 Manual Approval Submission Fixture Validator",
    "Phase 6 Signed Testnet Preparation Preview",
    "Phase 6.1 Signed Testnet Operator Unlock Request Template",
    "Phase 6.2 Operator Unlock Request Fixture Validator",
    "Phase 6.3 Signed Testnet Readiness Gate Review",
    "Phase 6.4 Signed Testnet Readiness Review Packet / Operator Decision Handoff",
    "Phase 6.5 Actual Manual Approval / Operator Unlock Intake Sandbox",
    "Phase 6.6 Actual Intake Validation Bridge for Phase 7 Entry Review",
    "Phase 7 Signed Testnet Validation Design / Disabled Executor Guard",
    "Phase 7.1 Signed Testnet Disabled Executor Fixture & Pre-submit Payload Guard",
    "Phase 7.1.1 Review Chain State Doctor",
    "Phase 7.2 Executor Enablement Review Packet",
    "Phase 7.3 Disabled Signed Testnet Executor Implementation Review",
    "Phase 7.4 Disabled Execution Reconciliation & Session Close",
]



@dataclass(frozen=True)
class StatusCheckResult:
    passed: bool
    failed_checks: list[str]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "failed_checks": self.failed_checks, "details": self.details}


def _read_text(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _load_yaml(root: Path, rel: str) -> dict[str, Any]:
    return yaml.safe_load(_read_text(root, rel)) or {}


def _load_pyproject(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def _current_title(readme: str) -> str:
    return readme.splitlines()[0].strip() if readme.splitlines() else ""


def _source_prefixes_from_script(text: str) -> set[str]:
    return set(re.findall(r'"(storage|data/reports|data/stores|dist)"', text))


def validate_status_consistency(root: str | Path = ".") -> StatusCheckResult:
    root = Path(root).resolve()
    failed: list[str] = []
    readme = _read_text(root, "README.md")
    settings = _load_yaml(root, "config/settings.yaml")
    pyproject = _load_pyproject(root)
    workflow = _read_text(root, ".github/workflows/review_only_chain_validation.yml")
    source_package_script = _read_text(root, "scripts/build_source_package.py")
    audit_bundle_script = _read_text(root, "scripts/build_audit_bundle.py")

    title = _current_title(readme)
    project_version = (settings.get("project") or {}).get("version")
    py_version = ((pyproject.get("project") or {}).get("version"))

    if EXPECTED_STEP not in title:
        failed.append("readme_title_current_step_mismatch")
    if "Step273 Signed Testnet Adapter Contract Preflight" in title:
        failed.append("readme_title_stale_step273")
    if project_version != EXPECTED_PROJECT_VERSION:
        failed.append("settings_project_version_mismatch")
    if py_version != EXPECTED_PYPROJECT_VERSION:
        failed.append("pyproject_version_mismatch")
    if EXPECTED_STEP not in readme or EXPECTED_PROJECT_VERSION not in readme:
        failed.append("readme_missing_current_step_or_project_version")
    master_context = _read_text(root, "CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md")
    for wording in DISABLED_WORDING:
        if wording not in readme:
            failed.append(f"readme_missing_disabled_wording:{wording}")
    for wording in AGENT_LIBRARY_DOC_WORDING:
        if wording not in readme:
            failed.append(f"readme_missing_agent_library_wording:{wording}")
        if wording not in master_context:
            failed.append(f"master_context_missing_agent_library_wording:{wording}")
    for rel_path in AGENT_LIBRARY_REQUIRED_PATHS:
        if not (root / rel_path).exists():
            failed.append(f"agent_library_required_path_missing:{rel_path}")
    for command in AGENT_LIBRARY_WORKFLOW_COMMANDS:
        if command not in workflow:
            failed.append(f"workflow_missing_agent_library_command:{command}")
    for pattern in ["tests/test_step282_*.py", "tests/test_step283_*.py", "tests/test_step284_*.py", "tests/test_step285_*.py", "tests/test_step286_*.py", "tests/test_step287_*.py", "tests/test_step288_*.py", "tests/test_step289_*.py", "tests/test_step290_*.py", "tests/test_step291_*.py", "tests/test_step292_*.py", "tests/test_step293_*.py", "tests/test_step294_*.py", "tests/test_step295_*.py", "tests/test_step296_*.py", "tests/test_step297_*.py", "tests/test_step298_*.py", "tests/test_step299_*.py", "tests/test_step300_*.py", "tests/test_step301_*.py", "tests/test_step302_*.py", "tests/test_step303_*.py", "tests/test_step304_*.py", "tests/test_step305_*.py", "tests/test_step306_*.py", "tests/test_step307_*.py", "tests/test_step308_*.py", "tests/test_step309_*.py", "tests/test_step310_*.py", "tests/test_step311_*.py", "tests/test_step312_*.py", "tests/test_step313_*.py", "tests/test_step314_*.py", "tests/test_step315_*.py", "tests/test_step316_*.py", "tests/test_step317_*.py", "tests/test_step318_*.py", "tests/test_step319_*.py", "tests/agents/"]:
        if pattern not in workflow:
            failed.append(f"workflow_missing_focused_regression_pattern:{pattern}")
    source_prefixes = _source_prefixes_from_script(source_package_script)
    if not SOURCE_EXCLUDED_PREFIXES.issubset(source_prefixes):
        failed.append("source_package_missing_runtime_exclusions")
    for prefix in VALIDATION_INCLUDED_PREFIXES:
        if f'"{prefix}"' not in audit_bundle_script:
            failed.append(f"validation_bundle_missing_evidence_prefix:{prefix}")

    # Runtime safety invariants from settings.
    safety = settings.get("safety") or {}
    execution = settings.get("execution") or {}
    explicit_packet = (execution.get("explicit_signed_testnet_execution_approval_packet") or {})
    readiness_packet = (execution.get("signed_testnet_execution_readiness_packet") or {})
    signed_gate = (execution.get("signed_testnet_gate") or {})
    read_only_probe = (execution.get("signed_testnet_read_only_venue_probe_session") or {})
    real_read_only_adapter = (execution.get("real_testnet_read_only_adapter") or {})
    secret_metadata_v2 = (execution.get("testnet_secret_metadata_intake_v2") or {})
    real_read_only_probe = (execution.get("real_read_only_venue_probe") or {})
    pre_submit_validator = (execution.get("signed_testnet_pre_submit_validator") or {})
    enablement_packet = (execution.get("signed_testnet_execution_enablement_packet") or {})
    order_executor = (execution.get("signed_testnet_order_executor") or {})
    venue_alignment = settings.get("venue_alignment") or {}
    venue_contract = settings.get("venue_contract") or {}
    if venue_alignment.get("primary_execution_venue") != "extended":
        failed.append("primary_execution_venue_not_extended")
    if venue_alignment.get("binance_branch_status") != "REFERENCE_ONLY_BINANCE_BRANCH":
        failed.append("binance_branch_not_reference_only")
    for flag in ("binance_reference_branch_runtime_enabled", "cross_venue_evidence_import_allowed", "runtime_auto_route_allowed"):
        if venue_alignment.get(flag) is not False:
            failed.append(f"venue_alignment_unsafe_flag:{flag}")
    if venue_contract.get("version") != "p70_venue_neutral_execution_contract_v1":
        failed.append("venue_contract_version_mismatch")
    for flag in ("endpoint_fields_allowed_in_core", "credential_values_allowed_in_core", "signing_algorithms_allowed_in_core", "network_enabled", "submit_enabled"):
        if venue_contract.get(flag) is not False:
            failed.append(f"venue_contract_unsafe_flag:{flag}")
    session_close_report = (execution.get("signed_testnet_session_close_report") or {})
    live_read_only_probe = (execution.get("live_read_only_adapter_probe") or {})
    live_key_scope_validator = (execution.get("live_key_scope_validator") or {})
    live_canary_approval_packet = (execution.get("live_canary_approval_packet") or {})
    live_canary_order_executor = (execution.get("live_canary_order_executor") or {})
    monitoring_alerting = (execution.get("monitoring_alerting") or {})
    deployment_runbook = (execution.get("deployment_runbook") or {})
    canary_outcome_report = (execution.get("canary_outcome_report") or {})
    runtime_flags = {
        "live_trading_enabled": safety.get("live_trading_enabled"),
        "testnet_signed_order_enabled": safety.get("testnet_signed_order_enabled"),
        "ready_for_signed_testnet_execution": explicit_packet.get("ready_for_signed_testnet_execution"),
        "testnet_order_submission_allowed": explicit_packet.get("testnet_order_submission_allowed"),
        "external_order_submission_allowed": explicit_packet.get("external_order_submission_allowed"),
        "external_order_submission_performed": explicit_packet.get("external_order_submission_performed"),
        "place_order_enabled": explicit_packet.get("place_order_enabled"),
        "cancel_order_enabled": explicit_packet.get("cancel_order_enabled"),
        "signed_order_executor_enabled": explicit_packet.get("signed_order_executor_enabled"),
        "readiness_place_order_enabled": readiness_packet.get("place_order_enabled"),
        "gate_place_order_enabled": signed_gate.get("place_order_enabled"),
        "probe_place_order_enabled": read_only_probe.get("place_order_enabled"),
        "real_read_only_adapter_place_order_enabled": real_read_only_adapter.get("place_order_enabled"),
        "real_read_only_adapter_cancel_order_enabled": real_read_only_adapter.get("cancel_order_enabled"),
        "real_read_only_adapter_testnet_order_submission_allowed": real_read_only_adapter.get("testnet_order_submission_allowed"),
        "real_read_only_adapter_external_order_submission_performed": real_read_only_adapter.get("external_order_submission_performed"),
        "real_read_only_adapter_signed_order_executor_enabled": real_read_only_adapter.get("signed_order_executor_enabled"),
        "secret_metadata_v2_api_key_value_access_allowed": secret_metadata_v2.get("api_key_value_access_allowed"),
        "secret_metadata_v2_api_secret_value_access_allowed": secret_metadata_v2.get("api_secret_value_access_allowed"),
        "secret_metadata_v2_secret_file_access_allowed": secret_metadata_v2.get("secret_file_access_allowed"),
        "secret_metadata_v2_secret_file_creation_allowed": secret_metadata_v2.get("secret_file_creation_allowed"),
        "secret_metadata_v2_ready_for_signed_testnet_execution": secret_metadata_v2.get("ready_for_signed_testnet_execution"),
        "secret_metadata_v2_testnet_order_submission_allowed": secret_metadata_v2.get("testnet_order_submission_allowed"),
        "secret_metadata_v2_external_order_submission_performed": secret_metadata_v2.get("external_order_submission_performed"),
        "secret_metadata_v2_place_order_enabled": secret_metadata_v2.get("place_order_enabled"),
        "secret_metadata_v2_cancel_order_enabled": secret_metadata_v2.get("cancel_order_enabled"),
        "secret_metadata_v2_signed_order_executor_enabled": secret_metadata_v2.get("signed_order_executor_enabled"),
        "real_read_only_probe_api_key_value_access_allowed": real_read_only_probe.get("api_key_value_access_allowed"),
        "real_read_only_probe_api_secret_value_access_allowed": real_read_only_probe.get("api_secret_value_access_allowed"),
        "real_read_only_probe_secret_file_access_allowed": real_read_only_probe.get("secret_file_access_allowed"),
        "real_read_only_probe_secret_file_creation_allowed": real_read_only_probe.get("secret_file_creation_allowed"),
        "real_read_only_probe_ready_for_signed_testnet_execution": real_read_only_probe.get("ready_for_signed_testnet_execution"),
        "real_read_only_probe_testnet_order_submission_allowed": real_read_only_probe.get("testnet_order_submission_allowed"),
        "real_read_only_probe_external_order_submission_performed": real_read_only_probe.get("external_order_submission_performed"),
        "real_read_only_probe_place_order_enabled": real_read_only_probe.get("place_order_enabled"),
        "real_read_only_probe_cancel_order_enabled": real_read_only_probe.get("cancel_order_enabled"),
        "real_read_only_probe_signed_order_executor_enabled": real_read_only_probe.get("signed_order_executor_enabled"),
        "pre_submit_api_key_value_access_allowed": pre_submit_validator.get("api_key_value_access_allowed"),
        "pre_submit_api_secret_value_access_allowed": pre_submit_validator.get("api_secret_value_access_allowed"),
        "pre_submit_secret_file_access_allowed": pre_submit_validator.get("secret_file_access_allowed"),
        "pre_submit_secret_file_creation_allowed": pre_submit_validator.get("secret_file_creation_allowed"),
        "pre_submit_ready_for_signed_testnet_execution": pre_submit_validator.get("ready_for_signed_testnet_execution"),
        "pre_submit_testnet_order_submission_allowed": pre_submit_validator.get("testnet_order_submission_allowed"),
        "pre_submit_external_order_submission_allowed": pre_submit_validator.get("external_order_submission_allowed"),
        "pre_submit_external_order_submission_performed": pre_submit_validator.get("external_order_submission_performed"),
        "pre_submit_place_order_enabled": pre_submit_validator.get("place_order_enabled"),
        "pre_submit_cancel_order_enabled": pre_submit_validator.get("cancel_order_enabled"),
        "pre_submit_signed_order_executor_enabled": pre_submit_validator.get("signed_order_executor_enabled"),
        "enablement_api_key_value_access_allowed": enablement_packet.get("api_key_value_access_allowed"),
        "enablement_api_secret_value_access_allowed": enablement_packet.get("api_secret_value_access_allowed"),
        "enablement_secret_file_access_allowed": enablement_packet.get("secret_file_access_allowed"),
        "enablement_secret_file_creation_allowed": enablement_packet.get("secret_file_creation_allowed"),
        "enablement_ready_for_signed_testnet_execution": enablement_packet.get("ready_for_signed_testnet_execution"),
        "enablement_testnet_order_submission_allowed": enablement_packet.get("testnet_order_submission_allowed"),
        "enablement_external_order_submission_allowed": enablement_packet.get("external_order_submission_allowed"),
        "enablement_external_order_submission_performed": enablement_packet.get("external_order_submission_performed"),
        "enablement_place_order_enabled": enablement_packet.get("place_order_enabled"),
        "enablement_cancel_order_enabled": enablement_packet.get("cancel_order_enabled"),
        "enablement_signed_order_executor_enabled": enablement_packet.get("signed_order_executor_enabled"),
        "enablement_runtime_settings_mutated": enablement_packet.get("runtime_settings_mutated"),
        "enablement_score_weights_mutated": enablement_packet.get("score_weights_mutated"),
        "enablement_auto_promotion_allowed": enablement_packet.get("auto_promotion_allowed"),

        "order_executor_api_key_value_access_allowed": order_executor.get("api_key_value_access_allowed"),
        "order_executor_api_secret_value_access_allowed": order_executor.get("api_secret_value_access_allowed"),
        "order_executor_secret_file_access_allowed": order_executor.get("secret_file_access_allowed"),
        "order_executor_secret_file_creation_allowed": order_executor.get("secret_file_creation_allowed"),
        "order_executor_ready_for_signed_testnet_execution": order_executor.get("ready_for_signed_testnet_execution"),
        "order_executor_testnet_order_submission_allowed": order_executor.get("testnet_order_submission_allowed"),
        "order_executor_external_order_submission_allowed": order_executor.get("external_order_submission_allowed"),
        "order_executor_external_order_submission_performed": order_executor.get("external_order_submission_performed"),
        "order_executor_place_order_enabled": order_executor.get("place_order_enabled"),
        "order_executor_cancel_order_enabled": order_executor.get("cancel_order_enabled"),
        "order_executor_signed_order_executor_enabled": order_executor.get("signed_order_executor_enabled"),
        "order_executor_adapter_write_routing_enabled": order_executor.get("adapter_write_routing_enabled"),
        "order_executor_runtime_settings_mutated": order_executor.get("runtime_settings_mutated"),
        "order_executor_score_weights_mutated": order_executor.get("score_weights_mutated"),
        "order_executor_auto_promotion_allowed": order_executor.get("auto_promotion_allowed"),

        "session_close_allow_signed_testnet_promotion": session_close_report.get("allow_signed_testnet_promotion"),
        "session_close_ready_for_signed_testnet_execution": session_close_report.get("ready_for_signed_testnet_execution"),
        "session_close_testnet_order_submission_allowed": session_close_report.get("testnet_order_submission_allowed"),
        "session_close_external_order_submission_allowed": session_close_report.get("external_order_submission_allowed"),
        "session_close_external_order_submission_performed": session_close_report.get("external_order_submission_performed"),
        "session_close_place_order_enabled": session_close_report.get("place_order_enabled"),
        "session_close_cancel_order_enabled": session_close_report.get("cancel_order_enabled"),
        "session_close_signed_order_executor_enabled": session_close_report.get("signed_order_executor_enabled"),
        "session_close_api_key_value_access_allowed": session_close_report.get("api_key_value_access_allowed"),
        "session_close_api_secret_value_access_allowed": session_close_report.get("api_secret_value_access_allowed"),
        "session_close_secret_file_access_allowed": session_close_report.get("secret_file_access_allowed"),
        "session_close_secret_file_creation_allowed": session_close_report.get("secret_file_creation_allowed"),
        "session_close_runtime_settings_mutated": session_close_report.get("runtime_settings_mutated"),
        "session_close_score_weights_mutated": session_close_report.get("score_weights_mutated"),
        "session_close_auto_promotion_allowed": session_close_report.get("auto_promotion_allowed"),

        "live_read_only_probe_live_canary_ready": live_read_only_probe.get("live_canary_ready"),
        "live_read_only_probe_live_key_scope_validated": live_read_only_probe.get("live_key_scope_validated"),
        "live_read_only_probe_live_order_submission_allowed": live_read_only_probe.get("live_order_submission_allowed"),
        "live_read_only_probe_external_order_submission_allowed": live_read_only_probe.get("external_order_submission_allowed"),
        "live_read_only_probe_external_order_submission_performed": live_read_only_probe.get("external_order_submission_performed"),
        "live_read_only_probe_place_order_enabled": live_read_only_probe.get("place_order_enabled"),
        "live_read_only_probe_cancel_order_enabled": live_read_only_probe.get("cancel_order_enabled"),
        "live_read_only_probe_withdrawal_enabled": live_read_only_probe.get("withdrawal_enabled"),
        "live_read_only_probe_transfer_enabled": live_read_only_probe.get("transfer_enabled"),
        "live_read_only_probe_leverage_mutation_enabled": live_read_only_probe.get("leverage_mutation_enabled"),
        "live_read_only_probe_margin_mode_mutation_enabled": live_read_only_probe.get("margin_mode_mutation_enabled"),
        "live_read_only_probe_signed_order_executor_enabled": live_read_only_probe.get("signed_order_executor_enabled"),
        "live_read_only_probe_api_key_value_access_allowed": live_read_only_probe.get("api_key_value_access_allowed"),
        "live_read_only_probe_api_secret_value_access_allowed": live_read_only_probe.get("api_secret_value_access_allowed"),
        "live_read_only_probe_secret_file_access_allowed": live_read_only_probe.get("secret_file_access_allowed"),
        "live_read_only_probe_secret_file_creation_allowed": live_read_only_probe.get("secret_file_creation_allowed"),
        "live_read_only_probe_runtime_settings_mutated": live_read_only_probe.get("runtime_settings_mutated"),
        "live_read_only_probe_score_weights_mutated": live_read_only_probe.get("score_weights_mutated"),
        "live_read_only_probe_auto_promotion_allowed": live_read_only_probe.get("auto_promotion_allowed"),

        "live_key_scope_validator_live_canary_ready": live_key_scope_validator.get("live_canary_ready"),
        "live_key_scope_validator_live_order_submission_allowed": live_key_scope_validator.get("live_order_submission_allowed"),
        "live_key_scope_validator_external_order_submission_allowed": live_key_scope_validator.get("external_order_submission_allowed"),
        "live_key_scope_validator_external_order_submission_performed": live_key_scope_validator.get("external_order_submission_performed"),
        "live_key_scope_validator_place_order_enabled": live_key_scope_validator.get("place_order_enabled"),
        "live_key_scope_validator_cancel_order_enabled": live_key_scope_validator.get("cancel_order_enabled"),
        "live_key_scope_validator_withdrawal_enabled": live_key_scope_validator.get("withdrawal_enabled"),
        "live_key_scope_validator_transfer_enabled": live_key_scope_validator.get("transfer_enabled"),
        "live_key_scope_validator_admin_enabled": live_key_scope_validator.get("admin_enabled"),
        "live_key_scope_validator_write_enabled": live_key_scope_validator.get("write_enabled"),
        "live_key_scope_validator_trade_enabled": live_key_scope_validator.get("trade_enabled"),
        "live_key_scope_validator_leverage_mutation_enabled": live_key_scope_validator.get("leverage_mutation_enabled"),
        "live_key_scope_validator_margin_mode_mutation_enabled": live_key_scope_validator.get("margin_mode_mutation_enabled"),
        "live_key_scope_validator_signed_order_executor_enabled": live_key_scope_validator.get("signed_order_executor_enabled"),
        "live_key_scope_validator_api_key_value_access_allowed": live_key_scope_validator.get("api_key_value_access_allowed"),
        "live_key_scope_validator_api_secret_value_access_allowed": live_key_scope_validator.get("api_secret_value_access_allowed"),
        "live_key_scope_validator_secret_file_access_allowed": live_key_scope_validator.get("secret_file_access_allowed"),
        "live_key_scope_validator_secret_file_creation_allowed": live_key_scope_validator.get("secret_file_creation_allowed"),
        "live_key_scope_validator_runtime_settings_mutated": live_key_scope_validator.get("runtime_settings_mutated"),
        "live_key_scope_validator_score_weights_mutated": live_key_scope_validator.get("score_weights_mutated"),
        "live_key_scope_validator_auto_promotion_allowed": live_key_scope_validator.get("auto_promotion_allowed"),

        "live_canary_approval_packet_live_canary_ready": live_canary_approval_packet.get("live_canary_ready"),
        "live_canary_approval_packet_live_order_submission_allowed": live_canary_approval_packet.get("live_order_submission_allowed"),
        "live_canary_approval_packet_external_order_submission_allowed": live_canary_approval_packet.get("external_order_submission_allowed"),
        "live_canary_approval_packet_external_order_submission_performed": live_canary_approval_packet.get("external_order_submission_performed"),
        "live_canary_approval_packet_place_order_enabled": live_canary_approval_packet.get("place_order_enabled"),
        "live_canary_approval_packet_cancel_order_enabled": live_canary_approval_packet.get("cancel_order_enabled"),
        "live_canary_approval_packet_withdrawal_enabled": live_canary_approval_packet.get("withdrawal_enabled"),
        "live_canary_approval_packet_transfer_enabled": live_canary_approval_packet.get("transfer_enabled"),
        "live_canary_approval_packet_admin_enabled": live_canary_approval_packet.get("admin_enabled"),
        "live_canary_approval_packet_write_enabled": live_canary_approval_packet.get("write_enabled"),
        "live_canary_approval_packet_trade_enabled": live_canary_approval_packet.get("trade_enabled"),
        "live_canary_approval_packet_leverage_mutation_enabled": live_canary_approval_packet.get("leverage_mutation_enabled"),
        "live_canary_approval_packet_margin_mode_mutation_enabled": live_canary_approval_packet.get("margin_mode_mutation_enabled"),
        "live_canary_approval_packet_signed_order_executor_enabled": live_canary_approval_packet.get("signed_order_executor_enabled"),
        "live_canary_approval_packet_api_key_value_access_allowed": live_canary_approval_packet.get("api_key_value_access_allowed"),
        "live_canary_approval_packet_api_secret_value_access_allowed": live_canary_approval_packet.get("api_secret_value_access_allowed"),
        "live_canary_approval_packet_secret_file_access_allowed": live_canary_approval_packet.get("secret_file_access_allowed"),
        "live_canary_approval_packet_secret_file_creation_allowed": live_canary_approval_packet.get("secret_file_creation_allowed"),
        "live_canary_approval_packet_runtime_settings_mutated": live_canary_approval_packet.get("runtime_settings_mutated"),
        "live_canary_approval_packet_score_weights_mutated": live_canary_approval_packet.get("score_weights_mutated"),
        "live_canary_approval_packet_auto_promotion_allowed": live_canary_approval_packet.get("auto_promotion_allowed"),

        "live_canary_order_executor_live_canary_execution_enabled": live_canary_order_executor.get("live_canary_execution_enabled"),
        "live_canary_order_executor_live_canary_ready": live_canary_order_executor.get("live_canary_ready"),
        "live_canary_order_executor_live_order_submission_allowed": live_canary_order_executor.get("live_order_submission_allowed"),
        "live_canary_order_executor_external_order_submission_allowed": live_canary_order_executor.get("external_order_submission_allowed"),
        "live_canary_order_executor_external_order_submission_performed": live_canary_order_executor.get("external_order_submission_performed"),
        "live_canary_order_executor_place_order_enabled": live_canary_order_executor.get("place_order_enabled"),
        "live_canary_order_executor_cancel_order_enabled": live_canary_order_executor.get("cancel_order_enabled"),
        "live_canary_order_executor_withdrawal_enabled": live_canary_order_executor.get("withdrawal_enabled"),
        "live_canary_order_executor_transfer_enabled": live_canary_order_executor.get("transfer_enabled"),
        "live_canary_order_executor_admin_enabled": live_canary_order_executor.get("admin_enabled"),
        "live_canary_order_executor_write_enabled": live_canary_order_executor.get("write_enabled"),
        "live_canary_order_executor_trade_enabled": live_canary_order_executor.get("trade_enabled"),
        "live_canary_order_executor_leverage_mutation_enabled": live_canary_order_executor.get("leverage_mutation_enabled"),
        "live_canary_order_executor_margin_mode_mutation_enabled": live_canary_order_executor.get("margin_mode_mutation_enabled"),
        "live_canary_order_executor_signed_order_executor_enabled": live_canary_order_executor.get("signed_order_executor_enabled"),
        "live_canary_order_executor_live_trading_enabled": live_canary_order_executor.get("live_trading_enabled"),
        "live_canary_order_executor_api_key_value_access_allowed": live_canary_order_executor.get("api_key_value_access_allowed"),
        "live_canary_order_executor_api_secret_value_access_allowed": live_canary_order_executor.get("api_secret_value_access_allowed"),
        "live_canary_order_executor_secret_file_access_allowed": live_canary_order_executor.get("secret_file_access_allowed"),
        "live_canary_order_executor_secret_file_creation_allowed": live_canary_order_executor.get("secret_file_creation_allowed"),
        "live_canary_order_executor_runtime_settings_mutated": live_canary_order_executor.get("runtime_settings_mutated"),
        "live_canary_order_executor_score_weights_mutated": live_canary_order_executor.get("score_weights_mutated"),
        "live_canary_order_executor_auto_promotion_allowed": live_canary_order_executor.get("auto_promotion_allowed"),

        "monitoring_alerting_telegram_send_enabled": monitoring_alerting.get("telegram_send_enabled"),
        "monitoring_alerting_telegram_message_sent": monitoring_alerting.get("telegram_message_sent"),
        "monitoring_alerting_external_notification_sent": monitoring_alerting.get("external_notification_sent"),
        "monitoring_alerting_webhook_called": monitoring_alerting.get("webhook_called"),
        "monitoring_alerting_email_sent": monitoring_alerting.get("email_sent"),
        "monitoring_alerting_live_trading_enabled": monitoring_alerting.get("live_trading_enabled"),
        "monitoring_alerting_live_order_submission_allowed": monitoring_alerting.get("live_order_submission_allowed"),
        "monitoring_alerting_external_order_submission_allowed": monitoring_alerting.get("external_order_submission_allowed"),
        "monitoring_alerting_external_order_submission_performed": monitoring_alerting.get("external_order_submission_performed"),
        "monitoring_alerting_place_order_enabled": monitoring_alerting.get("place_order_enabled"),
        "monitoring_alerting_cancel_order_enabled": monitoring_alerting.get("cancel_order_enabled"),
        "monitoring_alerting_api_key_value_access_allowed": monitoring_alerting.get("api_key_value_access_allowed"),
        "monitoring_alerting_api_secret_value_access_allowed": monitoring_alerting.get("api_secret_value_access_allowed"),
        "monitoring_alerting_secret_file_access_allowed": monitoring_alerting.get("secret_file_access_allowed"),
        "monitoring_alerting_secret_file_creation_allowed": monitoring_alerting.get("secret_file_creation_allowed"),
        "monitoring_alerting_runtime_settings_mutated": monitoring_alerting.get("runtime_settings_mutated"),
        "monitoring_alerting_score_weights_mutated": monitoring_alerting.get("score_weights_mutated"),
        "monitoring_alerting_auto_promotion_allowed": monitoring_alerting.get("auto_promotion_allowed"),

        "deployment_runbook_deployment_execution_enabled": deployment_runbook.get("deployment_execution_enabled"),
        "deployment_runbook_server_deployment_performed": deployment_runbook.get("server_deployment_performed"),
        "deployment_runbook_process_start_enabled": deployment_runbook.get("process_start_enabled"),
        "deployment_runbook_process_stop_enabled": deployment_runbook.get("process_stop_enabled"),
        "deployment_runbook_process_restart_enabled": deployment_runbook.get("process_restart_enabled"),
        "deployment_runbook_systemd_write_enabled": deployment_runbook.get("systemd_write_enabled"),
        "deployment_runbook_docker_run_enabled": deployment_runbook.get("docker_run_enabled"),
        "deployment_runbook_env_file_write_enabled": deployment_runbook.get("env_file_write_enabled"),
        "deployment_runbook_api_key_value_access_allowed": deployment_runbook.get("api_key_value_access_allowed"),
        "deployment_runbook_api_secret_value_access_allowed": deployment_runbook.get("api_secret_value_access_allowed"),
        "deployment_runbook_secret_file_access_allowed": deployment_runbook.get("secret_file_access_allowed"),
        "deployment_runbook_secret_file_creation_allowed": deployment_runbook.get("secret_file_creation_allowed"),
        "deployment_runbook_live_order_submission_allowed": deployment_runbook.get("live_order_submission_allowed"),
        "deployment_runbook_external_order_submission_allowed": deployment_runbook.get("external_order_submission_allowed"),
        "deployment_runbook_external_order_submission_performed": deployment_runbook.get("external_order_submission_performed"),
        "deployment_runbook_place_order_enabled": deployment_runbook.get("place_order_enabled"),
        "deployment_runbook_cancel_order_enabled": deployment_runbook.get("cancel_order_enabled"),
        "deployment_runbook_live_trading_enabled": deployment_runbook.get("live_trading_enabled"),
        "deployment_runbook_runtime_settings_mutated": deployment_runbook.get("runtime_settings_mutated"),
        "deployment_runbook_score_weights_mutated": deployment_runbook.get("score_weights_mutated"),
        "deployment_runbook_auto_promotion_allowed": deployment_runbook.get("auto_promotion_allowed"),
        "canary_outcome_report_live_scaled_promotion_allowed": canary_outcome_report.get("live_scaled_promotion_allowed"),
        "canary_outcome_report_live_trading_enabled": canary_outcome_report.get("live_trading_enabled"),
        "canary_outcome_report_live_order_submission_allowed": canary_outcome_report.get("live_order_submission_allowed"),
        "canary_outcome_report_runtime_settings_mutated": canary_outcome_report.get("runtime_settings_mutated"),
        "canary_outcome_report_score_weights_mutated": canary_outcome_report.get("score_weights_mutated"),
        "canary_outcome_report_auto_promotion_allowed": canary_outcome_report.get("auto_promotion_allowed"),
        "deployment_runbook_telegram_send_enabled": deployment_runbook.get("telegram_send_enabled"),
        "deployment_runbook_external_notification_sent": deployment_runbook.get("external_notification_sent"),
    }


    for name, value in runtime_flags.items():
        if value is not False:
            failed.append(f"runtime_flag_not_false:{name}")

    details = {
        "readme_title": title,
        "settings_project_version": project_version,
        "pyproject_version": py_version,
        "source_package_runtime_exclusions": sorted(source_prefixes),
        "runtime_flags": runtime_flags,
        "agent_library_workflow_commands": AGENT_LIBRARY_WORKFLOW_COMMANDS,
        "agent_library_required_paths": AGENT_LIBRARY_REQUIRED_PATHS,
    }
    return StatusCheckResult(passed=not failed, failed_checks=failed, details=details)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    root = Path(argv[0]) if argv else Path(".")
    result = validate_status_consistency(root)
    print(json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
