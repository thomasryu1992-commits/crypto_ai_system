# Step312 — Live Key Scope Validator Report

## Goal

Step312 adds a metadata-only Live Key Scope Validator on top of Step311 Live Read-only Adapter Probe. The validator checks whether a future live key reference is restricted to read-only/minimal scope before any live canary approval work can continue.

## Implemented files

- `src/crypto_ai_system/execution/live_key_scope_validator.py`
- `tests/test_step312_live_key_scope_validator.py`
- `config/settings.yaml`
- `run_full_cycle.py`
- `run_operational_dry_run.py`
- `scripts/status_consistency_checker.py`
- `.github/workflows/review_only_chain_validation.yml`
- `scripts/run_step280_full_regression.py`
- `README.md`
- `CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md`

## Runtime evidence

Step312 writes:

- `storage/latest/live_key_scope_validation.json`
- `storage/latest/live_key_scope_validator_registry_record.json`
- `storage/registries/live_key_scope_validator_registry.jsonl`

## Validation behavior

The validator requires:

- metadata-only live key reference
- valid `key_fingerprint_sha256`
- `environment=live` or `environment=mainnet`
- approved live venue metadata
- live base URL metadata
- read-only scope
- operator metadata
- IP whitelist metadata
- fresh Step311 live read-only probe evidence

It blocks:

- actual API key or API secret values
- secret file reads or creation
- non-metadata secret references
- non-live/testnet metadata
- trade/write/order scope
- withdrawal/transfer/admin scope
- leverage/margin mutation scope
- unsafe runtime flags
- missing or stale Step311 live read-only probe evidence

## Safety invariants

Step312 does not unlock live execution. These remain false:

- `live_canary_ready=false`
- `live_order_submission_allowed=false`
- `external_order_submission_allowed=false`
- `external_order_submission_performed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `withdrawal_enabled=false`
- `transfer_enabled=false`
- `signed_order_executor_enabled=false`
- `live_trading_enabled=false`
- `api_key_value_access_allowed=false`
- `api_secret_value_access_allowed=false`
- `secret_file_access_allowed=false`
- `secret_file_creation_allowed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `auto_promotion_allowed=false`

## Verification summary

- `compileall`: PASSED
- `status_consistency_checker`: PASSED
- `Step312 + Step282 tests`: 13 passed
- `Step303~Step312 tests`: 70 passed
- `Step294~Step312 tests`: 133 passed
- `Step281/282/288~293/299~312 focused tests`: 148 passed
- `Step258~Step265 tests`: 42 passed
- `Step266~Step272 tests`: 43 passed
- `Step273~Step280 tests`: 53 passed
- `run_full_cycle.py`: `BLOCK_DATA_HEALTH / NO_ORDER`
- `run_operational_dry_run.py`: PASSED

## Current full-cycle Step312 evidence

`live_key_scope_validation.status=LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY`

This means live key scope metadata is valid for review-only live canary preparation, but live canary and live order submission remain disabled.

## Next step

Step313 — Live Canary Approval Packet.
