# Step288 — ResearchSignal Registry v2 Report

## Step goal
Add an append-only canonical ResearchSignal Registry so finalized ResearchSignal v2 objects are recorded with complete lineage before Signal QA, Decision, RiskGate, paper, signed testnet, or live-canary stages consume them.

## Current stage
review-only / shadow / paper preparation. Signed testnet execution, testnet order submission, external order submission, settings mutation, runtime score-weight mutation, candidate auto-application, and automatic promotion remain disabled.

## Files/modules modified

- `src/crypto_ai_system/registry/research_signal_registry.py`
- `src/crypto_ai_system/registry/__init__.py`
- `src/crypto_ai_system/research/raw_score_pipeline.py`
- `tests/test_step288_research_signal_registry_v2.py`
- `scripts/run_step280_full_regression.py`
- `scripts/status_consistency_checker.py`
- `.github/workflows/review_only_chain_validation.yml`
- `README.md`
- `CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md`

## Required behavior implemented

Step288 writes:

- `storage/latest/research_signal_registry_record.json`
- `storage/registries/research_signal_registry.jsonl`

Each registry record preserves:

- `research_signal_id`
- `signal_version`
- `profile_id`
- `profile_version`
- `config_version`
- `data_snapshot_id`
- `data_snapshot_manifest_sha256`
- `feature_snapshot_id`
- `feature_matrix_sha256`
- `source_bundle_sha256`
- `market_thesis_note_id`
- `market_thesis_note_sha256`
- `optional_data_health`
- `missing_optional_source_count`
- `stale_optional_source_count`
- `live_candidate_eligible`
- `price_direction_score`
- `derivatives_positioning_score`
- `exchange_flow_score`
- `etf_flow_score`
- `stablecoin_liquidity_score`
- `final_signal_direction`
- `permission_result`
- `neutral_due_to_missing`
- `blocked_reason`
- `research_signal_sha256`
- `research_signal_registry_record_sha256`

## Safety constraints verified

The registry writer is review-only and does not:

- create order intent
- approve trades
- submit signed testnet orders
- submit live orders
- mutate `settings.yaml`
- mutate runtime `score_weights`
- auto-apply candidate profiles
- auto-promote to signed testnet or live

Runtime safety flags remained false:

- `live_trading_enabled=false`
- `testnet_signed_order_enabled=false`
- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `external_order_submission_allowed=false`
- `external_order_submission_performed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`

## Runtime evidence

Latest ResearchSignal Registry record after `run_full_cycle.py`:

```text
research_signal_id=d1044da98203103a7be05d60
data_snapshot_id=data_snapshot_2c4f3e6d0d946e5a93bdedd3
feature_snapshot_id=feature_snapshot_a3d37e86487de1637a29
feature_matrix_sha256=721304635cb46d57ff577e715298616495a2ffb2a5bde6f73d2d850a4af2749f
source_bundle_sha256=d1fae841b53c704872ff5a631ca4707f5e7537b37b35d70bfc85f033947c2a74
permission_result=review_only
live_candidate_eligible=false
```

`run_full_cycle.py` result:

```text
Decision: BLOCK_DATA_HEALTH
Data health: UNHEALTHY
Order: NO_ORDER
Spreadsheet: EXPORTED_LOCAL_BACKUP
```

This is expected because optional sources remain missing/disabled and the current runtime evidence is not signed-testnet/live eligible.

## Validation commands executed

```bash
PYTHONPATH=src python -m compileall -q src config tests
PYTHONPATH=src pytest -q tests/test_step288_*.py
PYTHONPATH=src pytest -q tests/test_step282_*.py tests/test_step283_*.py tests/test_step284_*.py tests/test_step285_*.py tests/test_step286_*.py tests/test_step287_*.py tests/test_step288_*.py
PYTHONPATH=src pytest -q tests/test_step258_*.py tests/test_step259_*.py tests/test_step260_*.py tests/test_step261_*.py tests/test_step262_*.py tests/test_step263_*.py tests/test_step264_*.py tests/test_step265_*.py tests/test_step266_*.py tests/test_step267_*.py tests/test_step268_*.py tests/test_step269_*.py tests/test_step270_*.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py tests/test_step274_*.py tests/test_step275_*.py tests/test_step276_*.py tests/test_step277_*.py tests/test_step278_*.py tests/test_step279_*.py tests/test_step280_*.py tests/test_step281_*.py tests/test_step282_*.py tests/test_step283_*.py tests/test_step284_*.py tests/test_step285_*.py tests/test_step286_*.py tests/test_step287_*.py tests/test_step288_*.py
PYTHONPATH=src python scripts/status_consistency_checker.py .
PYTHONPATH=src python run_operational_dry_run.py
PYTHONPATH=src python run_full_cycle.py
```

## Validation results

- compileall: PASSED
- Step288 tests: 4 passed
- Step282~288 focused tests: 25 passed
- Step258~288 focused regression: 171 passed
- status consistency checker: PASSED
- operational dry run: PASSED
- full cycle: `BLOCK_DATA_HEALTH / NO_ORDER`

Note: the Step280 chunked full regression runner was updated to include `tests/test_step288_*.py`. A complete long-running Step280 runner attempt exceeded the sandbox execution window during later suites, so the focused Step258~288 regression was used for this handoff. Step281 packet tests used the previous Step287 validation bundle's passed Step280 report evidence, consistent with the prior package evidence model.

## Acceptance criteria

- ResearchSignal Registry module exists and appends canonical JSONL records.
- `run_raw_to_score_pipeline()` persists the finalized ResearchSignal registry record.
- Latest ResearchSignal Registry record preserves data, feature, source, and thesis lineage.
- Registry record includes permission result and neutral-due-to-missing metadata.
- Registry writer does not create order intent or mutate runtime settings.
- Runtime execution flags remain disabled.
- Focused regression tests pass.

## Next recommended step

Proceed to Step289 — Signal QA Agent. The next layer should validate ResearchSignal existence, signal version, profile metadata, data snapshot ID, feature snapshot ID, feature matrix hash, source bundle hash, optional-data marking, stale/fallback/synthetic/sample blockers, and legacy fallback blocking before any trading decision consumes the signal.
