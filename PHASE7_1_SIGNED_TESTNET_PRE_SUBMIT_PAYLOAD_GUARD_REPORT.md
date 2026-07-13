# Phase 7.1 Signed Testnet Disabled Executor Fixture & Pre-submit Payload Guard

This phase adds review-only would-submit payload fixtures, pre-submit payload validation, and a disabled executor fixture guard.

It does not submit signed testnet orders, does not enable `place_order`, does not enable `cancel_order`, does not enable the signed executor, does not access secret values, and does not mutate runtime settings.

Expected status when Phase 7 design is ready:

`PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY`

Expected status without Phase 7 design readiness:

`PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_BLOCKED_REVIEW_ONLY`

Required invariant:

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
