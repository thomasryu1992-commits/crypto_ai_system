# Step306 — Signed Testnet Pre-submit Validator Report

## Goal

Step306 adds a review-only signed-testnet pre-submit validation layer. The validator creates pre-submit evidence for a would-submit testnet order payload only when the order intent, risk gate, real read-only venue probe, metadata-only secret reference, and canonical ID chain align. It does not submit orders and does not unlock signed testnet execution.

## Implemented files

- `src/crypto_ai_system/execution/signed_testnet_pre_submit_validator.py`
- `tests/test_step306_signed_testnet_pre_submit_validator.py`
- `run_full_cycle.py`
- `run_operational_dry_run.py`
- `config/settings.yaml`
- `README.md`
- `CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md`
- `scripts/status_consistency_checker.py`
- `scripts/run_step280_full_regression.py`
- `.github/workflows/review_only_chain_validation.yml`

## New evidence

- `storage/latest/signed_testnet_pre_submit_validation_report.json`
- `storage/latest/would_submit_order_payload.json`
- `storage/latest/signed_testnet_pre_submit_registry_record.json`
- `storage/signed_testnet_pre_submit/pre_submit_validation_report.json`
- `storage/signed_testnet_pre_submit/would_submit_order_payload.json`
- `storage/registries/signed_testnet_pre_submit_validator_registry.jsonl`

## Validation behavior

The validator checks:

- order intent exists and is created
- order intent stage is signed testnet/testnet
- canonical ID chain includes order intent, decision, risk gate, ResearchSignal, profile, symbol, and side
- risk gate exists and has `PASS_SIGNED_TESTNET`
- risk gate approval is true
- real read-only venue probe exists, is valid, testnet-only, fresh, and metadata-only
- unsafe submission flags remain false
- API key value/secret value/secret file access flags remain false

## Fail-closed statuses

The report uses:

- `SIGNED_TESTNET_PRE_SUBMIT_VALIDATED_REVIEW_ONLY`
- `SIGNED_TESTNET_PRE_SUBMIT_BLOCKED`

Block reasons include:

- `STEP306_BLOCK_MISSING_ORDER_INTENT`
- `STEP306_BLOCK_ORDER_INTENT_NOT_CREATED`
- `STEP306_BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET`
- `STEP306_BLOCK_MISSING_RISK_GATE`
- `STEP306_BLOCK_RISK_GATE_NOT_SIGNED_TESTNET`
- `STEP306_BLOCK_RISK_GATE_NOT_APPROVED`
- `STEP306_BLOCK_MISSING_VENUE_PROBE`
- `STEP306_BLOCK_VENUE_PROBE_INVALID`
- `STEP306_BLOCK_VENUE_PROBE_STALE`
- `STEP306_BLOCK_UNSAFE_SUBMISSION_FLAG`
- `STEP306_BLOCK_SECRET_VALUE_ACCESS`
- `STEP306_BLOCK_MISSING_CANONICAL_ID_CHAIN`

## Current full-cycle result

The current full cycle remains blocked before order submission:

```text
Decision: BLOCK_DATA_HEALTH
Data health: UNHEALTHY
Order: NO_ORDER
Signed testnet pre-submit: SIGNED_TESTNET_PRE_SUBMIT_BLOCKED
```

This is expected because current runtime evidence does not contain a signed-testnet order intent, a signed-testnet-approved risk gate, or a complete canonical pre-submit chain.

## Safety invariants

All remain disabled:

```text
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_allowed=false
external_order_submission_performed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
api_key_value_access_allowed=false
api_secret_value_access_allowed=false
secret_file_access_allowed=false
secret_file_creation_allowed=false
live_trading_enabled=false
testnet_signed_order_enabled=false
runtime_settings_mutated=false
score_weights_mutated=false
auto_promotion_allowed=false
```

## Validation summary

```text
compileall: PASSED
status_consistency_checker: PASSED
Step306 tests: 7 passed
Step282 + Step305 + Step306 tests: 19 passed
Step303~Step306 tests: 29 passed
Step294~Step306 tests: 92 passed
Step281/282/288~293/299~306 tests: 107 passed
Step258~Step265 tests: 42 passed
Step266~Step272 tests: 43 passed
Step273~Step280 tests: 53 passed
run_operational_dry_run.py: PASSED
run_full_cycle.py: BLOCK_DATA_HEALTH / NO_ORDER
```

## Next step

Proceed to Step307 — Signed Testnet Execution Enablement Packet. This packet must still remain disabled by default and must require manual approval, fresh Step305 probe evidence, valid Step306 pre-submit evidence, hard caps, kill switch recheck, and explicit operator unlock request.
