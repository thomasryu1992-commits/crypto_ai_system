# P51 External Evidence Import Bridge Dry-run

P51 adds a review-only dry-run bridge between P50 external evidence import validation and P7 post-submit evidence intake.

## Purpose

P50 verifies that operator-supplied, redacted external-runtime evidence is structurally safe to import. P51 checks whether that validated evidence would be accepted or rejected by the P7 post-submit evidence intake validator.

P51 does not submit orders, call endpoints, create signatures, read secrets, persist P7 status, or unlock runtime authority.

## Status

```text
P51_P7_IMPORT_BRIDGE_DRY_RUN_READY_REVIEW_ONLY_NO_SUBMIT
```

When a complete candidate is supplied to the in-memory builder, P51 may produce one of the following dry-run statuses:

```text
P51_P7_IMPORT_BRIDGE_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT
P51_P7_IMPORT_BRIDGE_DRY_RUN_REJECTED_REVIEW_ONLY_NO_SUBMIT
P51_P7_IMPORT_BRIDGE_DRY_RUN_BLOCKED_FAIL_CLOSED
```

## Required candidate sections

```text
p7_input_preview
status_polling_events
cancel_boundary_evidence
signed_testnet_reconciliation_evidence
signed_testnet_session_close_evidence
```

## Safety boundaries

- P51 may call P7 validation logic only in memory.
- P51 must not persist `p7_post_submit_evidence_intake_report.json` as a real P7 result.
- P51 must not write P7 valid status.
- P51 must not grant signed-testnet promotion, live canary execution, live scaled execution, or scheduler authority.
- P51 top-level execution flags must remain false.

## Next step

After P51, the next safe development step is P52: P7 accepted-evidence import packet staging. P52 should still remain review-only and should prepare the controlled operator import packet, not execute runtime order submission.
