from __future__ import annotations

from scripts.common import bootstrap

bootstrap()

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.agents.agent_library_contract_review import run_agent_library_contract_review_latest
from crypto_ai_system.agents.agent_output_validator import (
    build_agent_output_schema_validation_report,
    load_json_file,
    persist_agent_output_schema_validation_report,
)
from crypto_ai_system.registry.agent_contract_registry import generate_and_persist_agent_contract_registry
from scripts.lint_agents import build_agent_lint_report, persist_agent_lint_report
from scripts.validate_agent_contracts import build_agent_contract_validation_report, persist_agent_contract_validation_report
from scripts.run_agent_evals import persist_agent_eval_report

from collectors.market_data_collector import collect_market_data
from builders.market_snapshot import build_market_snapshot
from builders.market_context import build_market_context
from crypto_ai_system.research.research_engine import run_research_cycle
from crypto_ai_system.research.decision_engine import run_research_decision
from data_health.health_check import run_data_health_check
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from risk.risk_guard import run_risk_guard
from crypto_ai_system.trading.trading_cycle import run_trading_cycle
from bridge.research_trading_bridge import run_research_trading_bridge
from crypto_ai_system.execution.order_executor import run_order_executor
from crypto_ai_system.execution.reconciler import run_reconciler
from crypto_ai_system.feedback.outcome_analytics_v2 import run_outcome_analytics_latest
from crypto_ai_system.feedback.performance_report_generator import run_performance_report_latest
from crypto_ai_system.feedback.candidate_profile_registry import run_candidate_profile_latest
from crypto_ai_system.registry.prompt_profile_library import run_prompt_profile_library_latest
from crypto_ai_system.registry.approval_registry import run_approval_registry_latest
from crypto_ai_system.reports.settings_write_preview_guard import run_settings_write_preview_guard_latest
from crypto_ai_system.validation.phase4_outcome_candidate_feedback import persist_phase4_outcome_candidate_feedback_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import persist_phase6_2_operator_unlock_request_fixture_validator_report
from crypto_ai_system.validation.phase6_3_signed_testnet_readiness_gate_review import persist_phase6_3_signed_testnet_readiness_gate_review_report
from crypto_ai_system.validation.phase6_4_signed_testnet_readiness_review_packet import persist_phase6_4_signed_testnet_readiness_review_packet_report
from crypto_ai_system.validation.phase6_5_actual_manual_approval_operator_unlock_intake_sandbox import persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report
from crypto_ai_system.validation.phase6_6_actual_intake_validation_bridge import persist_phase6_6_actual_intake_validation_bridge_report
from crypto_ai_system.validation.phase7_signed_testnet_validation_design_guard import persist_phase7_signed_testnet_validation_design_guard_report
from crypto_ai_system.validation.phase7_1_signed_testnet_pre_submit_payload_guard import persist_phase7_1_signed_testnet_pre_submit_payload_guard_report
from crypto_ai_system.validation.review_chain_state_doctor import persist_phase7_1_review_chain_state_doctor_report
from crypto_ai_system.validation.phase7_2_executor_enablement_review_packet import persist_phase7_2_executor_enablement_review_packet_report
from crypto_ai_system.validation.phase7_3_disabled_signed_testnet_executor_review import persist_phase7_3_disabled_signed_testnet_executor_review_report
from crypto_ai_system.validation.phase7_4_disabled_execution_reconciliation_session_close import persist_phase7_4_disabled_execution_reconciliation_session_close_report
from crypto_ai_system.validation.phase7_5_reconciliation_session_close_review_packet import persist_phase7_5_reconciliation_session_close_review_packet_report
from crypto_ai_system.validation.phase7_6_disabled_signed_testnet_session_operator_handoff import persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report
from crypto_ai_system.validation.phase7_7_future_executor_review_prerequisite_design import persist_phase7_7_future_executor_review_prerequisite_design_report
from crypto_ai_system.validation.phase7_8_future_executor_approval_packet_template import persist_phase7_8_future_executor_approval_packet_template_report
from crypto_ai_system.validation.phase7_9_future_executor_approval_intake_validator import persist_phase7_9_future_executor_approval_intake_validator_report
from crypto_ai_system.validation.phase7_10_future_executor_approval_review_packet import persist_phase7_10_future_executor_approval_review_packet_report
from crypto_ai_system.validation.phase7_11_future_executor_enablement_design_review import persist_phase7_11_future_executor_enablement_design_review_report
from crypto_ai_system.validation.phase7_12_future_executor_enablement_guard_fixture import persist_phase7_12_future_executor_enablement_guard_fixture_report
from crypto_ai_system.validation.phase7_13_future_executor_enablement_review_packet import persist_phase7_13_future_executor_enablement_review_packet_report
from crypto_ai_system.validation.phase7_14_future_executor_operator_decision_packet import persist_phase7_14_future_executor_operator_decision_packet_report
from crypto_ai_system.reports.review_only_export_packet import run_review_only_export_packet_latest
from crypto_ai_system.execution.real_testnet_read_only_adapter import run_real_testnet_read_only_adapter_latest
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import run_testnet_secret_metadata_intake_latest
from crypto_ai_system.execution.real_read_only_venue_probe import run_real_read_only_venue_probe_latest
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import run_signed_testnet_pre_submit_validator_latest
from crypto_ai_system.execution.signed_testnet_execution_enablement_packet import run_signed_testnet_execution_enablement_packet_latest
from crypto_ai_system.execution.signed_testnet_order_executor import run_signed_testnet_order_executor_latest
from crypto_ai_system.execution.signed_testnet_reconciliation import run_signed_testnet_reconciliation_latest
from crypto_ai_system.execution.signed_testnet_session_close_report import run_signed_testnet_session_close_report_latest
from crypto_ai_system.execution.live_read_only_adapter_probe import run_live_read_only_adapter_probe_latest
from crypto_ai_system.execution.live_key_scope_validator import run_live_key_scope_validator_latest
from crypto_ai_system.execution.live_canary_approval_packet import run_live_canary_approval_packet_latest
from crypto_ai_system.execution.live_canary_order_executor import run_live_canary_order_executor_latest
from crypto_ai_system.execution.live_canary_reconciliation import run_live_canary_reconciliation_latest
from crypto_ai_system.execution.monitoring_alerting import run_monitoring_alerting_latest
from crypto_ai_system.execution.deployment_runbook import run_deployment_runbook_latest
from crypto_ai_system.execution.canary_outcome_report import run_canary_outcome_report_latest
from crypto_ai_system.execution.live_scaled_readiness_gate import run_live_scaled_readiness_gate_latest
from analysis.live_shadow import run_live_shadow_report
from crypto_ai_system.reports.limited_live_readiness import build_limited_live_readiness_report
from integrations.spreadsheet_exporter import export_spreadsheet_schema_v3


def _run_agent_library_review_chain() -> dict:
    cfg = load_config()
    root = cfg.root
    lint_report = build_agent_lint_report(root)
    persist_agent_lint_report(lint_report, root)

    contract_validation_report = build_agent_contract_validation_report(root)
    persist_agent_contract_validation_report(contract_validation_report, root)
    contract_registry = generate_and_persist_agent_contract_registry(cfg)

    sample_output_path = root / "agent_contracts" / "eval_cases" / "approval" / "valid_approval_intake.json"
    sample_output = load_json_file(sample_output_path).get("agent_output", {}) if sample_output_path.exists() else {}
    output_schema_report = build_agent_output_schema_validation_report([sample_output] if sample_output else [])
    persist_agent_output_schema_validation_report(cfg, output_schema_report)

    eval_result = persist_agent_eval_report(root)
    contract_review = run_agent_library_contract_review_latest(cfg)

    return {
        "agent_lint_report": lint_report,
        "agent_contract_validation_report": contract_validation_report,
        "agent_contract_index": contract_registry.get("index"),
        "agent_contract_registry_record": contract_registry.get("registry_record"),
        "agent_output_schema_validation_report": output_schema_report,
        "agent_eval_report": eval_result.get("report"),
        "agent_library_contract_review": contract_review,
    }


def run_full_cycle() -> dict:
    collect_market_data()
    build_market_snapshot()
    build_market_context()
    research = run_research_cycle()
    research_decision = run_research_decision()
    data_health = run_data_health_check()
    valid_price_lineage = persist_valid_price_lineage_artifacts()
    paper_data_quality_gate = persist_paper_data_quality_gate_report()
    paper_strategy_validation = persist_paper_strategy_validation_report()
    risk = run_risk_guard()
    trading = run_trading_cycle(allow_new_position=data_health.get("allow_trading") and risk.get("allow_new_position"))
    trade_decision = run_research_trading_bridge()
    order = run_order_executor()
    reconciliation = run_reconciler()
    outcome = run_outcome_analytics_latest()
    performance_report = run_performance_report_latest()
    candidate_profile = run_candidate_profile_latest()
    prompt_profile_library = run_prompt_profile_library_latest()
    approval_registry = run_approval_registry_latest()
    settings_write_preview = run_settings_write_preview_guard_latest()
    phase4_1_paper_outcome_sample_accumulation = persist_phase4_1_paper_outcome_sample_accumulation_report()
    phase4_outcome_candidate_feedback = persist_phase4_outcome_candidate_feedback_report()
    phase4_2_signal_drift_candidate_readiness = persist_phase4_2_signal_drift_candidate_readiness_report()
    phase4_3_research_signal_score_bucket_replay = persist_phase4_3_research_signal_score_bucket_replay_report()
    phase4_4_candidate_profile_review_packet = persist_phase4_4_candidate_profile_review_packet_report()
    phase5_manual_approval_intake_validation = persist_phase5_manual_approval_intake_validation_report()
    phase5_1_manual_approval_operator_handoff = persist_phase5_1_manual_approval_operator_handoff_report()
    phase5_2_manual_approval_submission_fixture_validator = persist_phase5_2_manual_approval_submission_fixture_validator_report()
    phase6_signed_testnet_preparation_preview = persist_phase6_signed_testnet_preparation_preview_report()
    phase6_1_signed_testnet_operator_unlock_request_template = persist_phase6_1_signed_testnet_operator_unlock_request_template_report()
    phase6_2_operator_unlock_request_fixture_validator = persist_phase6_2_operator_unlock_request_fixture_validator_report()
    phase6_3_signed_testnet_readiness_gate_review = persist_phase6_3_signed_testnet_readiness_gate_review_report()
    phase6_4_signed_testnet_readiness_review_packet = persist_phase6_4_signed_testnet_readiness_review_packet_report()
    phase6_5_actual_manual_approval_operator_unlock_intake_sandbox = persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report()
    phase6_6_actual_intake_validation_bridge = persist_phase6_6_actual_intake_validation_bridge_report()
    phase7_signed_testnet_validation_design_guard = persist_phase7_signed_testnet_validation_design_guard_report()
    phase7_1_signed_testnet_pre_submit_payload_guard = persist_phase7_1_signed_testnet_pre_submit_payload_guard_report()
    phase7_1_1_review_chain_state_doctor = persist_phase7_1_review_chain_state_doctor_report()
    phase7_2_executor_enablement_review_packet = persist_phase7_2_executor_enablement_review_packet_report()
    phase7_3_disabled_signed_testnet_executor_review = persist_phase7_3_disabled_signed_testnet_executor_review_report()
    phase7_4_disabled_execution_reconciliation_session_close = persist_phase7_4_disabled_execution_reconciliation_session_close_report()
    phase7_5_reconciliation_session_close_review_packet = persist_phase7_5_reconciliation_session_close_review_packet_report()
    phase7_6_disabled_signed_testnet_session_operator_handoff = persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()
    phase7_7_future_executor_review_prerequisite_design = persist_phase7_7_future_executor_review_prerequisite_design_report()
    phase7_8_future_executor_approval_packet_template = persist_phase7_8_future_executor_approval_packet_template_report()
    phase7_9_future_executor_approval_intake_validator = persist_phase7_9_future_executor_approval_intake_validator_report()
    phase7_10_future_executor_approval_review_packet = persist_phase7_10_future_executor_approval_review_packet_report()
    phase7_11_future_executor_enablement_design_review = persist_phase7_11_future_executor_enablement_design_review_report()
    phase7_12_future_executor_enablement_guard_fixture = persist_phase7_12_future_executor_enablement_guard_fixture_report()
    phase7_13_future_executor_enablement_review_packet = persist_phase7_13_future_executor_enablement_review_packet_report()
    phase7_14_future_executor_operator_decision_packet = persist_phase7_14_future_executor_operator_decision_packet_report()
    agent_library = _run_agent_library_review_chain()
    review_only_export_packet = run_review_only_export_packet_latest()
    real_testnet_read_only_adapter = run_real_testnet_read_only_adapter_latest()
    testnet_secret_metadata_intake = run_testnet_secret_metadata_intake_latest()
    real_read_only_venue_probe = run_real_read_only_venue_probe_latest()
    signed_testnet_pre_submit = run_signed_testnet_pre_submit_validator_latest(venue_probe=real_read_only_venue_probe)
    signed_testnet_execution_enablement = run_signed_testnet_execution_enablement_packet_latest(
        approval_registry_record=approval_registry,
        pre_submit_validation_report=signed_testnet_pre_submit,
        venue_probe=real_read_only_venue_probe,
    )
    signed_testnet_order_executor = run_signed_testnet_order_executor_latest(
        enablement_packet=signed_testnet_execution_enablement,
        would_submit_payload=signed_testnet_pre_submit.get("would_submit_order_payload"),
    )
    signed_testnet_reconciliation = run_signed_testnet_reconciliation_latest(
        execution_record=signed_testnet_order_executor,
        would_submit_payload=signed_testnet_pre_submit.get("would_submit_order_payload"),
    )
    signed_testnet_session_close = run_signed_testnet_session_close_report_latest(
        execution_record=signed_testnet_order_executor,
        reconciliation_record=signed_testnet_reconciliation,
        pre_submit_validation_report=signed_testnet_pre_submit,
        venue_probe=real_read_only_venue_probe,
        enablement_packet=signed_testnet_execution_enablement,
    )
    live_read_only_adapter_probe = run_live_read_only_adapter_probe_latest()
    live_key_scope_validation = run_live_key_scope_validator_latest(live_read_only_probe=live_read_only_adapter_probe)
    live_canary_approval_packet = run_live_canary_approval_packet_latest(
        signed_testnet_session_close_report=signed_testnet_session_close,
        live_read_only_probe=live_read_only_adapter_probe,
        live_key_scope_validation=live_key_scope_validation,
    )
    live_canary_order_executor = run_live_canary_order_executor_latest(
        approval_packet=live_canary_approval_packet,
    )
    live_canary_reconciliation = run_live_canary_reconciliation_latest(
        execution_record=live_canary_order_executor,
        approval_packet=live_canary_approval_packet,
    )
    monitoring_alerting = run_monitoring_alerting_latest(
        data_health=data_health,
        risk_guard=risk,
        order=order,
        signed_testnet_reconciliation=signed_testnet_reconciliation,
        signed_testnet_session_close=signed_testnet_session_close,
        live_canary_order_executor=live_canary_order_executor,
        live_canary_reconciliation=live_canary_reconciliation,
    )
    deployment_runbook = run_deployment_runbook_latest(monitoring_alerting=monitoring_alerting)
    canary_outcome_report = run_canary_outcome_report_latest(
        live_canary_reconciliation=live_canary_reconciliation,
        monitoring_alerting=monitoring_alerting,
        deployment_runbook=deployment_runbook,
    )
    live_scaled_readiness_gate = run_live_scaled_readiness_gate_latest(
        canary_outcome_report=canary_outcome_report,
    )
    shadow = run_live_shadow_report()
    limited_live = build_limited_live_readiness_report()
    spreadsheet = export_spreadsheet_schema_v3()
    return {
        "research": research,
        "research_decision": research_decision,
        "data_health": data_health,
        "valid_price_lineage": valid_price_lineage,
        "paper_data_quality_gate": paper_data_quality_gate,
        "paper_strategy_validation": paper_strategy_validation,
        "risk": risk,
        "trading": trading,
        "trade_decision": trade_decision,
        "order": order,
        "reconciliation": reconciliation,
        "outcome": outcome,
        "performance_report": performance_report,
        "candidate_profile": candidate_profile,
        "prompt_profile_library": prompt_profile_library,
        "approval_registry": approval_registry,
        "settings_write_preview": settings_write_preview,
        "phase4_outcome_candidate_feedback": phase4_outcome_candidate_feedback,
        "phase4_1_paper_outcome_sample_accumulation": phase4_1_paper_outcome_sample_accumulation,
        "phase4_2_signal_drift_candidate_readiness": phase4_2_signal_drift_candidate_readiness,
        "phase4_3_research_signal_score_bucket_replay": phase4_3_research_signal_score_bucket_replay,
        "phase4_4_candidate_profile_review_packet": phase4_4_candidate_profile_review_packet,
        "phase5_manual_approval_intake_validation": phase5_manual_approval_intake_validation,
        "phase5_1_manual_approval_operator_handoff": phase5_1_manual_approval_operator_handoff,
        "phase5_2_manual_approval_submission_fixture_validator": phase5_2_manual_approval_submission_fixture_validator,
        "phase6_signed_testnet_preparation_preview": phase6_signed_testnet_preparation_preview,
        "phase6_1_signed_testnet_operator_unlock_request_template": phase6_1_signed_testnet_operator_unlock_request_template,
        "phase6_2_operator_unlock_request_fixture_validator": phase6_2_operator_unlock_request_fixture_validator,
        "phase6_3_signed_testnet_readiness_gate_review": phase6_3_signed_testnet_readiness_gate_review,
        "phase6_4_signed_testnet_readiness_review_packet": phase6_4_signed_testnet_readiness_review_packet,
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": phase6_5_actual_manual_approval_operator_unlock_intake_sandbox,
        "phase6_6_actual_intake_validation_bridge": phase6_6_actual_intake_validation_bridge,
        "phase7_signed_testnet_validation_design_guard": phase7_signed_testnet_validation_design_guard,
        "phase7_1_signed_testnet_pre_submit_payload_guard": phase7_1_signed_testnet_pre_submit_payload_guard,
        "phase7_1_1_review_chain_state_doctor": phase7_1_1_review_chain_state_doctor,
        "phase7_2_executor_enablement_review_packet": phase7_2_executor_enablement_review_packet,
        "phase7_3_disabled_signed_testnet_executor_review": phase7_3_disabled_signed_testnet_executor_review,
        "phase7_4_disabled_execution_reconciliation_session_close": phase7_4_disabled_execution_reconciliation_session_close,
        "phase7_5_reconciliation_session_close_review_packet": phase7_5_reconciliation_session_close_review_packet,
        "phase7_6_disabled_signed_testnet_session_operator_handoff": phase7_6_disabled_signed_testnet_session_operator_handoff,
        "phase7_7_future_executor_review_prerequisite_design": phase7_7_future_executor_review_prerequisite_design,
        "phase7_8_future_executor_approval_packet_template": phase7_8_future_executor_approval_packet_template,
        "phase7_9_future_executor_approval_intake_validator": phase7_9_future_executor_approval_intake_validator,
        "phase7_10_future_executor_approval_review_packet": phase7_10_future_executor_approval_review_packet,
        "phase7_11_future_executor_enablement_design_review": phase7_11_future_executor_enablement_design_review,
        "phase7_12_future_executor_enablement_guard_fixture": phase7_12_future_executor_enablement_guard_fixture,
        "phase7_13_future_executor_enablement_review_packet": phase7_13_future_executor_enablement_review_packet,
        "phase7_14_future_executor_operator_decision_packet": phase7_14_future_executor_operator_decision_packet,
        "agent_library": agent_library,
        "review_only_export_packet": review_only_export_packet,
        "real_testnet_read_only_adapter": real_testnet_read_only_adapter,
        "testnet_secret_metadata_intake": testnet_secret_metadata_intake,
        "real_read_only_venue_probe": real_read_only_venue_probe,
        "signed_testnet_pre_submit": signed_testnet_pre_submit,
        "signed_testnet_execution_enablement": signed_testnet_execution_enablement,
        "signed_testnet_order_executor": signed_testnet_order_executor,
        "signed_testnet_reconciliation": signed_testnet_reconciliation,
        "signed_testnet_session_close": signed_testnet_session_close,
        "live_read_only_adapter_probe": live_read_only_adapter_probe,
        "live_key_scope_validation": live_key_scope_validation,
        "live_canary_approval_packet": live_canary_approval_packet,
        "live_canary_order_executor": live_canary_order_executor,
        "live_canary_reconciliation": live_canary_reconciliation,
        "monitoring_alerting": monitoring_alerting,
        "deployment_runbook": deployment_runbook,
        "canary_outcome_report": canary_outcome_report,
        "live_scaled_readiness_gate": live_scaled_readiness_gate,
        "shadow": shadow,
        "limited_live": limited_live,
        "spreadsheet": spreadsheet,
    }


def main() -> None:
    result = run_full_cycle()
    print("Full cycle completed.")
    print("Decision:", result["trade_decision"]["final_decision"])
    print("Data health:", result["data_health"]["status"])
    print("Valid price lineage:", result["valid_price_lineage"]["status"])
    print("Paper data quality gate:", result["paper_data_quality_gate"]["status"])
    print("Paper strategy validation:", result["paper_strategy_validation"]["status"])
    print("Phase 4 outcome/candidate feedback:", result["phase4_outcome_candidate_feedback"]["status"])
    print("Phase 4.1 paper outcome sample accumulation:", result["phase4_1_paper_outcome_sample_accumulation"]["status"])
    print("Phase 4.2 signal drift candidate readiness:", result["phase4_2_signal_drift_candidate_readiness"]["status"])
    print("Phase 4.3 ResearchSignal score bucket replay:", result["phase4_3_research_signal_score_bucket_replay"]["status"])
    print("Phase 4.4 candidate profile review packet:", result["phase4_4_candidate_profile_review_packet"]["status"])
    print("Phase 5 manual approval intake validation:", result["phase5_manual_approval_intake_validation"]["status"])
    print("Phase 5.1 manual approval operator handoff:", result["phase5_1_manual_approval_operator_handoff"]["status"])
    print("Phase 5.2 manual approval fixture validator:", result["phase5_2_manual_approval_submission_fixture_validator"]["status"])
    print("Phase 6 signed testnet preparation preview:", result["phase6_signed_testnet_preparation_preview"]["status"])
    print("Phase 6.1 operator unlock request template:", result["phase6_1_signed_testnet_operator_unlock_request_template"]["status"])
    print("Phase 6.2 operator unlock fixture validator:", result["phase6_2_operator_unlock_request_fixture_validator"]["status"])
    print("Phase 6.3 signed testnet readiness gate review:", result["phase6_3_signed_testnet_readiness_gate_review"]["status"])
    print("Phase 6.4 signed testnet readiness review packet:", result["phase6_4_signed_testnet_readiness_review_packet"]["status"])
    print("Phase 6.5 actual manual approval/operator unlock intake sandbox:", result["phase6_5_actual_manual_approval_operator_unlock_intake_sandbox"]["status"])
    print("Phase 6.6 actual intake validation bridge:", result["phase6_6_actual_intake_validation_bridge"]["status"])
    print("Phase 7 signed testnet validation design guard:", result["phase7_signed_testnet_validation_design_guard"]["status"])
    print("Phase 7.1 signed testnet pre-submit payload guard:", result["phase7_1_signed_testnet_pre_submit_payload_guard"]["status"])
    print("Phase 7.1.1 review chain state doctor:", result["phase7_1_1_review_chain_state_doctor"]["status"])
    print("Phase 7.2 executor enablement review packet:", result["phase7_2_executor_enablement_review_packet"]["status"])
    print("Phase 7.3 disabled signed testnet executor review:", result["phase7_3_disabled_signed_testnet_executor_review"]["status"])
    print("Phase 7.4 disabled execution reconciliation/session close:", result["phase7_4_disabled_execution_reconciliation_session_close"]["status"])
    print("Phase 7.5 reconciliation/session close review packet:", result["phase7_5_reconciliation_session_close_review_packet"]["status"])
    print("Phase 7.6 disabled signed testnet session operator handoff:", result["phase7_6_disabled_signed_testnet_session_operator_handoff"]["status"])
    print("Phase 7.7 future executor review prerequisite design:", result["phase7_7_future_executor_review_prerequisite_design"]["status"])
    print("Phase 7.8 future executor approval packet template:", result["phase7_8_future_executor_approval_packet_template"]["status"])
    print("Phase 7.9 future executor approval intake validator:", result["phase7_9_future_executor_approval_intake_validator"]["status"])
    print("Phase 7.10 future executor approval review packet:", result["phase7_10_future_executor_approval_review_packet"]["status"])
    print("Phase 7.11 future executor enablement design review:", result["phase7_11_future_executor_enablement_design_review"]["status"])
    print("Phase 7.12 future executor enablement guard fixture:", result["phase7_12_future_executor_enablement_guard_fixture"]["status"])
    print("Phase 7.13 future executor enablement review packet:", result["phase7_13_future_executor_enablement_review_packet"]["status"])
    print("Phase 7.14 future executor operator decision packet:", result["phase7_14_future_executor_operator_decision_packet"]["status"])
    print("Order:", result["order"]["status"])
    print("Live canary order executor:", result["live_canary_order_executor"]["status"])
    print("Live canary reconciliation:", result["live_canary_reconciliation"]["status"])
    print("Monitoring alerting:", result["monitoring_alerting"]["status"])
    print("Deployment runbook:", result["deployment_runbook"]["status"])
    print("Canary outcome report:", result["canary_outcome_report"]["status"])
    print("Live scaled readiness gate:", result["live_scaled_readiness_gate"]["status"])
    print("Spreadsheet:", result["spreadsheet"]["status"])


if __name__ == "__main__":
    main()
