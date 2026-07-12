# Step258 Feature Store → ResearchSignal v2 → Trading Permission Gate

## Scope

Step258 connects the additional BTC data layer into the canonical research/trading decision path without enabling live execution.

The connected flow is:

```text
Price Direction
+ Derivatives Positioning
+ Exchange Flow
+ ETF Flow
+ Stablecoin Liquidity
+ Risk Controls
= ResearchSignal v2 trade_permission
= Trading Bot permission gate before paper trade candidate creation
```

## Implemented behavior

1. Additional feature groups are consumed through the timestamp-safe Feature Store matrix:
   - `binance_derivatives_features`
   - `exchange_flow_features`
   - `etf_flow_features`
   - `stablecoin_liquidity_features`

2. Feature Store matrix version is locked as:

```text
step258_feature_store_permission_matrix
```

3. ResearchSignal v2 version is locked as:

```text
research_signal_v2_step258_feature_store_permission_gate
```

4. Missing optional data remains neutral:
   - `binance_derivatives_score = 0.0`
   - `exchange_flow_score = 0.0`
   - `etf_flow_score = 0.0`
   - `stablecoin_liquidity_score = 0.0`

5. Live and backtest Feature Store behavior remains separated:
   - live matrix can attach the latest optional snapshot only to the latest row
   - backtest matrix only attaches optional data where `feature_timestamp <= price_timestamp`

6. ResearchSignal v2 emits trade permission fields:
   - `allow_long`
   - `allow_short`
   - `allow_new_position`
   - `risk_level`: `normal`, `reduced`, `blocked`
   - `risk_warnings`
   - `block_reasons`

7. Trading Bot consumes ResearchSignal v2 as the hard pre-entry permission gate.
   - `normal`: full configured paper risk
   - `reduced`: reduced position sizing
   - `blocked`: no trade plan

## Safety boundary

Step258 does not port or enable canonical live/testnet execution.

The following Step257 decisions remain intact:

```text
execution.live_executor = disabled compatibility surface
execution.testnet_executor = disabled compatibility surface
missing_canonical_module_count = 2
root package deletion = deferred
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
```

## Validation

Added regression file:

```text
tests/test_step258_feature_store_researchsignal_permission_gate.py
```

Covered cases:

1. Supportive extra data flows through Feature Store into ResearchSignal v2 and creates a Trading Bot paper trade candidate.
2. Missing optional data defaults to neutral and does not break Feature Store or ResearchSignal generation.
3. Risk-off exchange flow / ETF flow / stablecoin liquidity blocks the trade before Trading Bot plan generation.
