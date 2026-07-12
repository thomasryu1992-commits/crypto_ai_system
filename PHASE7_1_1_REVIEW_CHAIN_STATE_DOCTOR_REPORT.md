# Phase 7.1.1 — One-command Review Chain Runner & Artifact State Doctor

This phase adds a review-only state doctor and one-command runner for the Phase 2.1 → Phase 7.1 validation chain.

It diagnoses stale or missing artifacts, recreates review-only approval/operator convenience fixtures from current templates, and reruns the review chain in the correct order. It does not enable signed testnet execution, submit orders, read secrets, mutate settings, or promote any candidate.

Primary command:

```powershell
python scripts\run_phase7_1_review_chain.py
```

Generated evidence:

- `storage/latest/review_chain_state_doctor_report.json`
- `storage/latest/phase7_1_1_review_chain_state_doctor_report.json`
- `storage/latest/PHASE7_1_1_REVIEW_CHAIN_OPERATOR_HANDOFF.md`

All execution flags remain disabled:

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
