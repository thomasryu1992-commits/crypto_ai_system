# Phase 6.2 Operator Unlock Request Fixture Validator — Review Only

Phase 6.2 adds review-only fixture validation for signed testnet operator unlock requests.

It creates valid and invalid operator unlock request fixtures under `storage/signed_testnet/fixtures/` and verifies that:

- a well-formed fixture can pass review-only validation,
- missing operator signature fails closed,
- hash mismatch fails closed,
- missing hard cap fails closed,
- kill switch not rechecked fails closed,
- unsafe unlock/order flags fail closed.

This phase deliberately does **not** create `storage/latest/operator_unlock_request.json` or `storage/signed_testnet/operator_unlock_request.json`.

Disabled invariants remain:

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `auto_promotion_allowed=false`
