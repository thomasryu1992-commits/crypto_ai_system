# Step328 Full Agent Role Expansion Report

Step328 expands the Agent Library contract layer from the initial approval/risk/QA contracts into full role-separated markdown contracts across research, trading, execution, feedback, QA, and approval.

## Added Contract Groups

- research: `research_signal_builder`, `research_signal_qa_agent`, `signal_drift_detector`
- trading: `trading_decision_reviewer`, `price_structure_reviewer`, `permission_boundary_auditor`
- execution: `paper_execution_auditor`, `reconciliation_auditor`, `order_intent_chain_validator`
- feedback: `outcome_feedback_analyst`, `performance_report_builder`, `candidate_profile_reviewer`
- qa: `evidence_collector`, `regression_runtime_hygiene_agent`
- approval: `export_packet_agent`

## Safety Result

All expanded agent contracts are review-only instruction contracts. They keep `can_modify_runtime=false`, `can_submit_orders=false`, `runtime_mutation_performed=false`, and `order_submission_performed=false`. Agent Library validation remains evidence-only and cannot unlock signed testnet, live canary, or live scaled execution.

## Verification Scope

Step328 adds `tests/agents/test_step328_full_agent_role_expansion.py` to verify required contracts, divisions, safe permissions, eval case paths, and review-only index flags.
