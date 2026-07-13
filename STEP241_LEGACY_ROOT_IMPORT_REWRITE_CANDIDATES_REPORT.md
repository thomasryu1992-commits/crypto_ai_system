# Step241 v5 Legacy Root Import Rewrite Candidate Patch Validation Report

## Scope

Step241 rewrites only LOW-risk legacy root imports with exact canonical module matches.

During validation, Step241 also repaired canonical compatibility exports where exact module paths existed but legacy public names were not yet available.

This is not production/live-trading validation.

## Result

- Overall: `PASS_WITH_TARGETED_VALIDATION`
- compileall `src config tests scripts`: `PASS`
- targeted pytest: `19 passed`
- import retirement plan generation: `PASS`
- legacy root package audit: `PASS`
- Step209~Step237 chain smoke: `PASS`
- source ZIP hygiene: `PASS`

## Full Pytest Note

A full `python -m pytest -q tests` run was attempted but exceeded the interactive execution window. The Step241 impact surface was validated with targeted tests covering the rewritten imports and related modules.

Recommended local/CI command:

```bash
python -m pytest -q tests
```

## Import Retirement Result

Before Step241:

```text
direct_root_import_finding_count: 29
LOW-risk rewrite candidates: 4
MANUAL_MAPPING_REQUIRED: 25
```

After Step241:

```text
direct_root_import_finding_count: 25
LOW-risk rewrite candidates remaining: 0
MANUAL_MAPPING_REQUIRED: 25
```

## Files Rewritten

- `run_step164_permission_telegram_validation.py`
- `tests/test_step150_safety.py`
- `tests/test_step163_trading_permission_gate.py`
- `tests/test_step164_permission_audit_telegram_report.py`

## Canonical Compatibility Exports Added

- `crypto_ai_system.execution.idempotency.make_client_order_id`
- backward-compatible positional signature for `crypto_ai_system.execution.idempotency.make_idempotency_key`
- `crypto_ai_system.trading.permission_gate.signal_payload_from_research_signal`
- `crypto_ai_system.trading.permission_audit.log_permission_gate_audit`

## Current Migration Status

`manual_mapping_required_remaining`

Root-level `execution`, `trading`, and `research` still exist as legacy compatibility packages. Thin wrapper conversion is still blocked until the 25 manual mapping imports are resolved.

## Important Safety Boundary

Step241 does not enable:

- paper execution
- adapter routing
- external API submission
- Telegram real send
- live trading

Correct validation label:

`Step209~Step237 chain/artifact-generation validation passed`

Do not describe this as production/live-trading validation.
