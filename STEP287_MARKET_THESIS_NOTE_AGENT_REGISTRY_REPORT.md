# Step287 — Market Thesis Note Agent / Registry Report

## Goal

Add a review-only Market Thesis Note layer between Feature Matrix generation and ResearchSignal generation. The note converts feature evidence into human-readable bullish, bearish, neutral, counterargument, invalidation, supporting-feature, conflicting-feature, and open-risk sections without creating orders or mutating runtime settings.

## Implementation Summary

### Added modules

```text
src/crypto_ai_system/research/market_thesis_note.py
src/crypto_ai_system/registry/market_thesis_registry.py
```

### Modified modules

```text
src/crypto_ai_system/research/research_bot.py
src/crypto_ai_system/research/research_signal_builder.py
src/crypto_ai_system/research/raw_score_pipeline.py
src/crypto_ai_system/registry/__init__.py
scripts/status_consistency_checker.py
scripts/run_step280_full_regression.py
.github/workflows/review_only_chain_validation.yml
README.md
```

## Behavior Added

```text
Feature Matrix
→ Market Thesis Note
→ ResearchSignal
```

The Market Thesis Note now carries:

```text
market_thesis_note_id
thesis_version
profile_id
profile_version
config_version
data_snapshot_id
data_snapshot_manifest_sha256
feature_snapshot_id
feature_matrix_sha256
source_bundle_sha256
optional_data_health
missing_optional_source_count
stale_optional_source_count
live_candidate_eligible
main_market_question
core_thesis
long_arguments
short_arguments
neutral_arguments
counterarguments
invalidation_conditions
supporting_features
conflicting_features
open_risks
created_at_utc
market_thesis_note_sha256
```

## Registry Added

```text
storage/registries/market_thesis_registry.jsonl
```

Registry records are append-only summaries and include:

```text
market_thesis_note_id
thesis_version
data_snapshot_id
feature_snapshot_id
feature_matrix_sha256
source_bundle_sha256
market_thesis_note_sha256
argument counts
invalidation count
review-only safety flags
registry record hash
```

## Safety Constraints Preserved

```text
order_intent_created=false
trade_approved=false
runtime_settings_mutated=false
score_weights_mutated=false
live_trading_enabled=false
testnet_signed_order_enabled=false
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
```

## Runtime Compatibility Note

Step287 is additive. Runtime `project.version` and package version remain:

```text
project.version=step286_researchsignal_feature_lineage_fix
pyproject version=0.286.0
```

This preserves Step273~286 test compatibility while README and validation wording identify the current source handoff as Step287.

## Tests Added

```text
tests/test_step287_market_thesis_note_agent_registry.py
```

Covered behavior:

```text
Market Thesis Note preserves data/feature/source lineage
Market Thesis Note stays review-only and does not create order intent
Market Thesis Registry appends summary records
ResearchBot creates Market Thesis Note before ResearchSignal
ResearchSignal carries market_thesis_note_id and market_thesis_note_sha256
```

## Validation Results

```text
compileall:
PASSED

Step287 tests:
3 passed

Step280 + Step282 + Step287 compatibility tests:
13 passed

Step282~287 focused tests:
21 passed

Step258~287 focused regression:
167 passed

status_consistency_checker:
PASSED

run_operational_dry_run.py:
PASSED

run_full_cycle.py:
BLOCK_DATA_HEALTH / NO_ORDER
```

The full chunked Step280 regression runner was attempted in this sandbox but did not finish before tool timeout. The Step281 tests were run against the existing passed Step280 full-regression evidence from the prior validation bundle, and the Step258~287 focused regression passed.

## Runtime Evidence After Full Cycle

```text
storage/latest/market_thesis_note.json: generated
storage/latest/market_thesis_registry_record.json: generated
storage/registries/market_thesis_registry.jsonl: appended
```

Latest Market Thesis Note lineage:

```text
data_snapshot_id=data_snapshot_2c4f3e6d0d946e5a93bdedd3
feature_snapshot_id=feature_snapshot_a3d37e86487de1637a29
feature_matrix_sha256=721304635cb46d57ff577e715298616495a2ffb2a5bde6f73d2d850a4af2749f
source_bundle_sha256=d1fae841b53c704872ff5a631ca4707f5e7537b37b35d70bfc85f033947c2a74
live_candidate_eligible=false
order_intent_created=false
trade_approved=false
runtime_settings_mutated=false
```

## Next Recommended Step

Step288 — ResearchSignal Registry v2.

Goal:

```text
Store canonical ResearchSignal v2 objects in append-only research_signal_registry.jsonl with signal hash, lineage IDs, optional data health, live_candidate_eligible flag, missing/stale optional source counts, and no legacy fallback usage.
```
