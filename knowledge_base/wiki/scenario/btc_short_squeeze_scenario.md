# BTC Short Squeeze Scenario

## Status
active

## Direction
bullish

## Core Thesis
If BTC holds above key support while derivatives positioning remains elevated, a reclaim above trigger can force shorts to cover.

## Current Context
Current price: 64159.9. Setup levels are strategy fallbacks unless a dynamic setup engine overrides them.

## Conditions
- BTC holds above 106200.0
- BTC reclaims 107500.0
- OI remains elevated
- Funding does not overheat
- Spot CVD improves

## Invalidation
- BTC trades below 106200.0
- OI drops sharply with price
- Spot CVD remains negative
- Exchange inflow increases

## Trading Implication
Create conditional long watch. Trigger: 107500.0, invalidation: 106200.0, take profit: 110000.0.

## Related Concepts
- [[concept/open_interest]]
- [[concept/funding_rate]]
- [[concept/cvd]]
- [[concept/liquidation_heatmap]]

## Related Entities
- [[entity/BTC]]

## Confidence
medium

## Last Updated
2026-06-22T10:28:11.665259+00:00
