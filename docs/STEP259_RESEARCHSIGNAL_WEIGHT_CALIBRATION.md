# Step259 ResearchSignal v2 Weight Calibration and Permission Distribution

## Goal

Step259 adds a review-only calibration layer after the Step258 Feature Store / ResearchSignal v2 / Trading Bot permission gate connection.

The goal is not to select a final production strategy. The goal is to make ResearchSignal v2 score-weight changes measurable before they affect paper or live execution decisions.

## Scope

Step259 covers:

1. ResearchSignal v2 candidate score-weight profiles.
2. Replay-style score comparison against a Feature Store matrix.
3. `normal / reduced / blocked` permission distribution reporting.
4. Telegram daily report extra-data summary fields.
5. Safety boundary preservation from Step257 and Step258.

## Candidate score-weight profiles

The following profiles are available through `research.score_weight_profiles` and `crypto_ai_system.research.research_signal_calibration`:

- `baseline_step258`
- `price_structure_dominant`
- `flow_confirmed`
- `liquidity_risk_guarded`

All profiles are normalized before use. The calibration module does not mutate the active runtime configuration and does not place orders.

## Calibration output

The Step259 calibration report records, per profile:

- rows evaluated
- average total score
- permission distribution
  - normal
  - reduced
  - blocked
- side distribution
  - LONG
  - SHORT
  - FLAT
- entry allowed count and ratio
- blocked ratio
- reduced ratio
- block reason counts
- risk warning counts

The report is written to:

```text
data/reports/step259_researchsignal_weight_calibration_report.json
```

## Telegram extra-data summary

Telegram daily reports now include an extra-data section that surfaces:

- Binance derivatives score
- exchange flow score
- ETF flow score
- stablecoin liquidity score
- exchange netflow 30D z-score
- ETF 5D flow
- stablecoin 7D supply change

This keeps daily reports aligned with the ResearchSignal v2 formula:

```text
Price Direction
+ Derivatives Positioning
+ Exchange Flow
+ ETF Flow
+ Stablecoin Liquidity
= ResearchSignal
```

## Safety boundary

Step259 remains review-only:

```text
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
missing_canonical_module_count = 2
root_package_deletion_deferred = true
```

`execution.live_executor` and `execution.testnet_executor` remain explicit disabled compatibility surfaces.
