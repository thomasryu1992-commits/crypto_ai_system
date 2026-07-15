# Phase 4.1 Paper Outcome Sample Accumulation Report

This package adds a review-only paper outcome sample accumulator.

Scope:
- Replays the valid local price/feature matrix over multiple recent windows.
- Creates closed paper-only outcome samples using TP / SL / time-based close logic.
- Persists outcome feedback registry records.
- Generates a performance report from accumulated closed outcomes.
- Creates a candidate profile draft only when performance criteria are met.
- Creates a disabled settings-write preview only; it never applies settings.

Safety invariants:
- No exchange adapter call.
- No API key or secret access.
- No signed testnet or live order submission.
- No runtime settings mutation.
- No score_weights mutation.
- No automatic approval or promotion.
