# Phase 9.2 Separate One-Order Runtime Submit Approval Packet / No Order Submit

This package adds a review-only approval packet and validator for a separately explicit operator approval before any one-order signed testnet runtime submit can be considered.

It does not submit orders, call order/private endpoints, create signatures, read secrets, enable executors, or mutate runtime settings. A validated approval packet is evidence only and keeps `real_testnet_submit_may_begin=false`.

## Scope
- Testnet only
- BTCUSDT only
- One order only
- Max notional 10 USDT
- No live/mainnet approval
- Fresh hot-path risk refresh required at action time
- Runtime secret binding required locally at action time
- Duplicate submit lock required
- Post-submit immediate relock required
- Phase 9.3/9.4 handle status polling and reconciliation separately

## Default State
The default package state awaits a user/operator-filled approval JSON and remains blocked/fail-closed.
