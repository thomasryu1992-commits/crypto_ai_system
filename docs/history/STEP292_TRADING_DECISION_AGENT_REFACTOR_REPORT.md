# Step292 Trading Decision Agent Refactor Report

## Goal

Refactor the bridge between ResearchSignal/trading-signal permission and order-intent creation so that:

1. Price structure is responsible for direction, entry, stop loss, take profit, risk/reward, and invalidation preview.
2. ResearchSignal-derived permission is responsible for allow/reduce/block/review-only permission.
3. PreOrderRiskGate is required before any OrderIntent can be created.
4. Trading Decision remains review-only and never submits, routes, or mutates runtime settings.

## Modified Files

```text
src/crypto_ai_system/trading/trading_decision_agent.py
bridge/research_trading_bridge.py
src/crypto_ai_system/execution/order_executor.py
README.md
CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md
scripts/status_consistency_checker.py
scripts/run_step280_full_regression.py
.github/workflows/review_only_chain_validation.yml
tests/test_step282_canonical_status_sync.py
tests/test_step292_trading_decision_agent_refactor.py
```

## New Behavior

### Trading Decision Agent

New module:

```text
src/crypto_ai_system/trading/trading_decision_agent.py
```

The agent builds a review-only trading decision candidate with:

```text
price_structure.direction
price_structure.entry
price_structure.stop_loss
price_structure.take_profit
price_structure.risk_reward
price_structure.invalidation_conditions
research_permission.permission_result
research_permission.allow_long
research_permission.allow_short
research_permission.allow_new_position
pre_order_risk_gate_required=true
allow_order_intent=false unless future risk gate approval exists and intent creation is enabled outside this module
```

### Bridge Refactor

`bridge/research_trading_bridge.py` now delegates to the Trading Decision Agent and writes Step292 decision evidence to `latest_trade_decision.json`. It also appends decision context to `decision_pipeline_registry.jsonl`.

### Order Executor Guard

`build_order_intent()` now fails closed even if legacy callers pass `allow_order_intent=true`, unless:

```text
pre_order_risk_gate_approved=true
risk_gate_id exists
```

This preserves the rule that PreOrderRiskGate is required before OrderIntent.

## Runtime Evidence

`run_full_cycle.py` result:

```text
Decision: BLOCK_DATA_HEALTH
Data health: UNHEALTHY
Order: NO_ORDER
Spreadsheet: EXPORTED_LOCAL_BACKUP
```

Latest trade decision evidence:

```text
final_decision=BLOCK_DATA_HEALTH
direction=NONE
allow_new_position=false
allow_order_intent=false
pre_order_risk_gate_required=true
pre_order_risk_gate_approved=false
order_intent_block_reason=PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT
order_intent_created=false
```

Latest order intent evidence:

```text
status=NO_ORDER_INTENT
state=REJECTED
pre_order_risk_gate_required=true
pre_order_risk_gate_approved=false
order_intent_block_reason=PRE_ORDER_RISK_GATE_REQUIRED_BEFORE_ORDER_INTENT
order_intent_created=false
```

## Safety Invariants

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
automatic promotion disabled
```

## Validation

```text
compileall: PASSED
status_consistency_checker: PASSED
Step292 tests: 5 passed
Step282 + Step288 + Step289 + Step290 + Step291 + Step292 focused tests: 37 passed
Step258~Step280 focused tests: 138 passed
Step281~Step292 focused tests: 61 passed
Operational dry run: PASSED
Full cycle: BLOCK_DATA_HEALTH / NO_ORDER
```

A single monolithic Step258~Step292 command exceeded sandbox timeout while individual chunks passed. No failing tests remained after chunked validation.

## Acceptance Criteria

```text
Trading Decision does not create OrderIntent: PASSED
RiskGate required before OrderIntent: PASSED
Legacy allow_order_intent=true blocked without risk_gate_id: PASSED
Price structure preview exists for aligned setups: PASSED
Research permission remains separate from price structure: PASSED
Decision pipeline registry still records missing future IDs explicitly: PASSED
Live/testnet/order submission remains disabled: PASSED
```

## Next Step

Proceed to Step293 — PreOrderRiskGate Full Policy Expansion.
