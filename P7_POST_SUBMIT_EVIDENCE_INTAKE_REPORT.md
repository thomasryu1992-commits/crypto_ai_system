# P7 Post-submit Evidence Intake Report

Status: `P7_POST_SUBMIT_EVIDENCE_INTAKE_WAITING_FOR_EXTERNAL_SUBMIT_REVIEW_ONLY`

## Purpose

P7 adds the post-submit evidence intake boundary for a future separately approved single signed testnet order. It does not submit an order. The default latest artifact remains waiting/review-only because the current package has no real external signed testnet submit evidence.

## Added files

- `src/crypto_ai_system/execution/post_submit_evidence_intake.py`
- `scripts/build_p7_post_submit_evidence_intake.py`
- `tests/agents/test_p7_post_submit_evidence_intake.py`

## Evidence outputs

- `storage/latest/p7_post_submit_evidence_intake_report.json`
- `storage/latest/p7_post_submit_evidence_intake_summary.json`
- `storage/latest/p7_post_submit_evidence_intake_negative_fixture_results.json`
- `storage/latest/p7_post_submit_evidence_intake_registry_record.json`
- `storage/p7_post_submit_evidence_intake/p7_post_submit_evidence_intake_report.json`

## Default safety posture

- `external_submit_evidence_present=false`
- `post_submit_chain_complete=false`
- `actual_order_submission_performed=false`
- `actual_testnet_order_submitted=false`
- `order_endpoint_called=false`
- `order_status_endpoint_called=false`
- `cancel_endpoint_called=false`
- `secret_value_accessed=false`
- `signed_testnet_promotion_allowed=false`
- `live_canary_preparation_allowed=false`
- `live_canary_execution_enabled=false`
- `live_scaled_execution_enabled=false`

## Implemented validation chain

When a separate local runtime eventually submits exactly one signed testnet order, P7 validates:

1. Source P6 runtime action evidence and hash linkage.
2. Post-submit exchange order ID intake.
3. Status polling evidence.
4. Cancel boundary evidence.
5. Signed testnet reconciliation evidence.
6. Signed testnet session close evidence.

A complete external-submitted synthetic fixture reaches `P7_POST_SUBMIT_EVIDENCE_INTAKE_RECONCILED_SESSION_CLOSED_REVIEW_ONLY`, but still grants no promotion or live/canary authority.

## Negative fixtures

The P7 negative fixture set blocks:

- Missing exchange order ID.
- Source P6 hash mismatch.
- Status endpoint secret leak.
- Open-status cancel boundary without a valid cancel decision.
- Reconciliation mismatch.
- Session close promotion enabled.
- Mainnet scope in order intake.

## Verification

Focused regression:

```bash
PYTHONPATH=src:. pytest -q \
  tests/agents/test_p7_post_submit_evidence_intake.py \
  tests/agents/test_p6_single_signed_testnet_submit_runtime_action.py \
  tests/agents/test_p5_action_time_submit_approval_boundary.py \
  tests/agents/test_p4_signed_testnet_one_order_runtime_package.py \
  tests/test_step309_signed_testnet_reconciliation.py \
  tests/test_step310_signed_testnet_session_close_report.py
```

Result: `42 passed`

Additional focused regression:

```bash
PYTHONPATH=src:. pytest -q \
  tests/agents/test_phase9_2_single_testnet_runtime_submit_wrapper.py \
  tests/agents/test_phase9_2_real_submit_enablement_gate.py \
  tests/agents/test_phase9_2_submit_guard_recheck.py \
  tests/agents/test_phase10_signed_testnet_session_validation_blocked_design.py
```

Result: `13 passed`

Additional checks:

- `compileall`: passed
- `status_consistency_checker.py`: passed
- `lint_agents.py`: passed
- `validate_agent_contracts.py`: passed
- `validate_agent_outputs.py`: passed
- `run_agent_evals.py`: passed

## Next stage

P8 should implement repeated clean signed testnet session validation. It should consume multiple completed P7 session-close evidence records and block promotion unless the configured minimum clean session count, mismatch/error/slippage/latency thresholds, kill-switch checks, and scenario coverage requirements are met.
