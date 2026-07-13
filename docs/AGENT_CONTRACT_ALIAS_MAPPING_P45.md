# P45 Agent Contract Alias Mapping

This table makes the exact Phase 7.15-7.17/P45 directive filenames traceable without granting runtime authority.

| Required alias filename | Existing mapped contract | Purpose |
|---|---|---|
| `operator_decision_intake_template_agent.md` | `agents/approval/operator_supplied_approval_fixture_agent.md` | Phase 7.15 operator decision intake template alias |
| `operator_decision_intake_validator_agent.md` | `agents/approval/single_signed_testnet_enablement_intake_agent.md` | Phase 7.16 intake validator alias |
| `final_pre_executor_review_agent.md` | `agents/execution/final_pre_submit_checklist_agent.md` | Phase 7.17 final pre-executor review alias |
| `disabled_executor_evidence_reviewer.md` | `agents/execution/blocked_executor_wrapper_agent.md` | Disabled executor evidence review alias |
| `disabled_reconciliation_session_close_reviewer.md` | `agents/execution/status_cancel_reconciliation_blocked_design_agent.md` | Disabled reconciliation/session-close review alias |
| `future_executor_approval_reviewer.md` | `agents/approval/signed_testnet_unlock_preview_agent.md` | Future executor approval review alias |
| `enablement_design_reviewer.md` | `agents/execution/real_submit_enablement_gate_agent.md` | Enablement design review alias |
| `enablement_guard_fixture_reviewer.md` | `agents/execution/submit_guard_recheck_agent.md` | Enablement guard fixture review alias |
| `operator_decision_packet_reviewer.md` | `agents/execution/manual_final_confirmation_agent.md` | Operator decision packet review alias |

All alias contracts keep `can_modify_runtime=false` and `can_submit_orders=false`; they are review-only traceability contracts, not executors.
