# Step305 — Real Read-only Venue Probe Report

## Goal

Step305 links the Step303 real testnet read-only adapter evidence with the Step304 metadata-only testnet secret reference evidence. It validates read-only venue probe readiness without enabling signed testnet execution, testnet order submission, place_order, cancel_order, external submission, secret value access, settings mutation, score-weight mutation, or live trading.

## Implemented changes

- Added `src/crypto_ai_system/execution/real_read_only_venue_probe.py`.
- Added `tests/test_step305_real_read_only_venue_probe.py`.
- Connected Step305 into `run_full_cycle.py` and `run_operational_dry_run.py`.
- Added `execution.real_read_only_venue_probe` review-only configuration in `config/settings.yaml`.
- Updated status consistency checker, workflow, full-regression runner, README, and master context to Step305.

## Generated evidence

- `storage/latest/real_read_only_venue_probe.json`
- `storage/latest/real_read_only_venue_probe_registry_record.json`
- `storage/registries/real_read_only_venue_probe_registry.jsonl`

## Validation behavior

The probe validates:

- Step303 adapter evidence exists and is ready for read-only testnet probe.
- Step304 secret metadata intake exists and validates as metadata-only testnet reference.
- Venue and environment match.
- All required read probes are present, valid, and fresh.
- Balance, positions, open orders, orderbook, fee estimate, slippage estimate, min order size, and fetch-order probes have canonical timestamps.
- Place/cancel/order submission remain disabled.
- API key value, API secret value, secret file read, and secret file creation remain disabled.

## Current runtime result

`run_full_cycle.py` result:

```text
Decision: BLOCK_DATA_HEALTH
Data health: UNHEALTHY
Order: NO_ORDER
Real Read-only Venue Probe: REAL_READ_ONLY_VENUE_PROBE_VALID
```

The `NO_ORDER` result is expected. Step305 is a read-only venue probe stage and does not unlock signed testnet or live execution.

## Safety invariants

```text
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_performed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
api_key_value_access_allowed=false
api_secret_value_access_allowed=false
secret_file_access_allowed=false
secret_file_creation_allowed=false
live_trading_enabled=false
auto_promotion_allowed=false
```

## Regression results

```text
compileall: PASSED
status_consistency_checker: PASSED
Step303~Step305 tests: 22 passed
Step294~Step305 tests: 85 passed
Step281/282/288~293/299~305 tests: 100 passed
Step258~Step265 tests: 42 passed
Step266~Step272 tests: 43 passed
Step273~Step277 tests: 33 passed
Step278~Step280 tests: 20 passed
run_operational_dry_run.py: PASSED
run_full_cycle.py: BLOCK_DATA_HEALTH / NO_ORDER
```

## Next recommended step

Step306 — Signed Testnet Pre-submit Validator.

This next step should build would-submit payload validation and idempotency evidence while keeping actual order submission disabled.
