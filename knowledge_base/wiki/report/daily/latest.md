# Daily Crypto Market Report - 2026-06-22

## Market Summary
BTC is trading around 64159.9. Data mode: market_snapshot_builder. The structure is neutral-to-bullish, but confirmation is required before entry.

## Key Observations
- Price signal: mild_up
- Open interest signal: rising
- Funding signal: overheated_positive
- Long/short signal: long_crowded
- Liquidation signal: short_liquidation_dominant

## Active Scenarios
1. [[scenario/btc_short_squeeze_scenario]]
2. [[scenario/btc_breakdown_scenario]]

## Trading Bias
neutral_to_bullish

## Conditional Setup
- Setup Type: breakout_reclaim
- Direction: long
- Trigger: 107500.0
- Invalidation: 106200.0
- Take Profit: 110000.0
- Expires After Hours: 24

## Risk Notes
- Avoid entry if funding overheats.
- Avoid entry if spot CVD remains negative.
- Do not enter if KB lint status is ERROR.
- Fallback setup levels must be reviewed before live trading.

## Evidence
- [[source/coinalyze]]
- [[entity/BTC]]
- [[concept/open_interest]]
- [[concept/funding_rate]]
- [[concept/cvd]]

## Final Decision
Create conditional watch, not market order.

## Last Updated
2026-06-22T10:28:11.665259+00:00
