# Step258 Report — Feature Store / ResearchSignal v2 / Trading Permission Gate

## Result

Step258 completed the connection from the additional BTC data layer into the research/trading decision path.

## Main changes

- Locked Feature Store matrix version to `step258_feature_store_permission_matrix`.
- Locked ResearchSignal v2 version to `research_signal_v2_step258_feature_store_permission_gate`.
- Confirmed the four optional feature groups are connected into the Feature Store:
  - Binance derivatives positioning
  - Coin Metrics exchange flow
  - Farside BTC ETF flow
  - DefiLlama stablecoin liquidity
- Confirmed ResearchSignal v2 includes the new scoring components:
  - `exchange_flow_score`
  - `etf_flow_score`
  - `stablecoin_liquidity_score`
  - `risk_score`
- Confirmed Trading Bot uses ResearchSignal v2 `trade_permission` before creating a paper trade plan.

## Safety status

No live execution was enabled.

```text
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
missing_canonical_module_count = 2
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
```

## New test coverage

```text
tests/test_step258_feature_store_researchsignal_permission_gate.py
```

Test coverage locks:

1. Extra Feature Store data feeds ResearchSignal v2 and Trading Bot permission gate.
2. Missing optional data defaults to neutral.
3. Risk-off optional data blocks the trade before paper trade plan creation.
