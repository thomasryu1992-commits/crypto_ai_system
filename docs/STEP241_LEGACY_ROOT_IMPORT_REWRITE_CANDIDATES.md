# Step241 v5 Legacy Root Import Rewrite Candidate Patch

## Purpose

Step241 rewrites only LOW-risk legacy root imports that have exact canonical module matches.

## Rewrite Scope

Only these import patterns are eligible:

- `from trading.permission_audit import ...`
- `from trading.permission_gate import ...`
- `from execution.idempotency import ...`

These are rewritten to:

- `from crypto_ai_system.trading.permission_audit import ...`
- `from crypto_ai_system.trading.permission_gate import ...`
- `from crypto_ai_system.execution.idempotency import ...`

## What Step241 Does Not Do

- Does not rewrite `MANUAL_MAPPING_REQUIRED` imports.
- Does not convert root packages into thin wrappers.
- Does not delete root packages.
- Does not enable paper execution, adapter routing, external API calls, Telegram real sends, or live trading.

## Expected Result

- Direct root import finding count should decrease from 29 to 25.
- LOW-risk rewrite candidates should decrease from 4 to 0.
- Remaining imports should be manual mapping candidates.

## Compatibility Export Repair

During validation, Step241 confirmed that exact canonical module paths existed, but some canonical modules did not yet expose the same public names as the legacy callers expected.

Step241 therefore adds compatibility exports to canonical modules before keeping the import rewrites:

- `crypto_ai_system.execution.idempotency.make_client_order_id`
- backward-compatible positional signature for `crypto_ai_system.execution.idempotency.make_idempotency_key`
- `crypto_ai_system.trading.permission_gate.signal_payload_from_research_signal`
- `crypto_ai_system.trading.permission_audit.log_permission_gate_audit`

This keeps the rewrite safe while preserving existing tests.
