# Step291 — Decision Pipeline Registry Report

## Purpose

Step291 adds an append-only Decision Pipeline Registry that records research-decision lineage after ResearchSignal QA and legacy fallback blocking. The registry is audit evidence only. It does not create order intent, route orders, mutate settings, mutate score weights, submit signed testnet orders, or promote profiles.

## Added Modules

```text
src/crypto_ai_system/registry/decision_pipeline_registry.py
```

## Modified Modules / Files

```text
src/crypto_ai_system/research/decision_engine.py
src/crypto_ai_system/registry/__init__.py
scripts/status_consistency_checker.py
scripts/run_step280_full_regression.py
.github/workflows/review_only_chain_validation.yml
README.md
CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md
tests/test_step282_canonical_status_sync.py
tests/test_step291_decision_pipeline_registry.py
```

## New Runtime Evidence

```text
storage/registries/decision_pipeline_registry.jsonl
storage/latest/decision_pipeline_registry_record.json
```

## Canonical ID Chain Fields

```text
data_snapshot_id
feature_snapshot_id
research_signal_id
profile_id
approval_packet_id
approval_intake_id
decision_id
risk_gate_id
order_intent_id
execution_id
reconciliation_id
outcome_id
feedback_cycle_id
```

## Behavior

At the current review-only decision stage, the required current-stage chain is:

```text
data_snapshot_id
feature_snapshot_id
research_signal_id
profile_id
decision_id
```

Future-stage IDs are not inferred or regenerated. Missing future IDs are recorded explicitly in `missing_canonical_id_fields`.

## Safety Posture

All runtime-impacting paths remain disabled:

```text
live_trading_enabled=false
testnet_signed_order_enabled=false
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_allowed=false
external_order_submission_performed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
runtime_settings_mutated=false
score_weights_mutated=false
trade_approved=false
```

## Validation Results

```text
compileall:
PASSED

status_consistency_checker:
PASSED

Step291 tests:
5 passed

Step282 + Step288 + Step289 + Step290 + Step291 focused tests:
32 passed

Step258~Step291 focused regression:
194 passed

run_operational_dry_run.py:
PASSED

run_full_cycle.py:
BLOCK_DATA_HEALTH / NO_ORDER
```

## Runtime Evidence Summary

Latest `decision_pipeline_registry_record.json` after `run_full_cycle.py` preserved:

```text
data_snapshot_id=data_snapshot_2c4f3e6d0d946e5a93bdedd3
feature_snapshot_id=feature_snapshot_a3d37e86487de1637a29
research_signal_id=d1044da98203103a7be05d60
profile_id=default_review_profile
decision_id=decision_9953ec0e680b871695ee5b40
decision_stage=review_only
current_stage_id_chain_complete=true
full_canonical_id_chain_complete=false
missing_canonical_id_fields=approval_packet_id, approval_intake_id, risk_gate_id, order_intent_id, execution_id, reconciliation_id, outcome_id, feedback_cycle_id
```

## Acceptance Criteria

- Decision Pipeline Registry append-only JSONL exists.
- `run_research_decision()` writes a latest registry mirror.
- Data Snapshot, Feature Snapshot, ResearchSignal, Profile, and Decision IDs are preserved at decision stage.
- Missing approval/order/execution/outcome/feedback IDs are explicit.
- Registry does not create order intent.
- Registry does not mutate settings or score weights.
- Registry does not approve trades.
- Source handoff excludes runtime artifacts.
- Validation bundle may include runtime evidence.
