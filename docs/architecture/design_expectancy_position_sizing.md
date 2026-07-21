# Design: Expectancy-Based Position Sizing (deferred implementation)

Status: **decided, not implemented**. Decisions recorded 2026-07-21 so
implementation can start without re-litigating them; revise here first if a
decision changes. Prerequisite: enough independent trade events accumulated
across market regimes (see PR #51 — today every strategy sits at 1-2 events,
so any sizing scheme would resolve to the base tier anyway).

## Problem

Every paper order uses a fixed notional (~20 USDT). Once strategies have
statistically distinct, validated expectancies, sizing them identically leaves
edge on the table; sizing them by *unvalidated* expectancy amplifies noise.

## Decisions (locked until revised)

### D1. Feedback-loop boundary: operator-approved sizing profile

Sizing multipliers derived from performance data are a feedback loop into the
order path. The system's core principle is that feedback produces candidates
and NEVER mutates runtime. Therefore:

- The feedback layer emits a **sizing profile candidate** (per-strategy tier
  assignments + the evidence behind them), exactly like the existing candidate
  profile pattern.
- The candidate takes effect only after **manual operator approval** (same
  intake pattern as the live profile approval).
- No auto-application, no per-cycle drift. `runtime_settings_mutated` stays
  false everywhere.

### D2. Formula: discrete tiers, not Kelly

Kelly-style sizing needs win-rate/payoff estimates that are meaningless at the
current sample size and amplify estimation error. Start with discrete tiers on
**independent trade events** (PR #51 counting — never raw closed rows):

| Tier | Condition (per strategy) | Multiplier |
|---|---|---|
| base | default / insufficient evidence | 1.0x |
| validated | >= 10 independent events AND expectancy > 0 across >= 2 regimes | 1.5x |
| proven | >= 30 independent events AND expectancy > 0 across >= 3 regimes | 2.0x |

Any missing datum resolves to the LOWER tier (fail-closed). Fractional Kelly
is a possible future refinement once a strategy has hundreds of events.

### D3. Attribution unit: strategy_id, sample unit: independent events

- Research signals are per-cycle and never accumulate; **strategy_id** (S8
  attribution) is the unit that persists and owns an expectancy.
- Sample counts use `independent_trade_events` from `outcome_analytics_v2`.
  Raw closed counts re-introduce the repeat-counting bug fixed in PR #51.
- Regime coverage uses the outcome `regime` tag (also PR #51).

### D4. Application point: the bridge, composed multiplicatively

- The multiplier applies where notional is decided today: the
  research/strategy bridge (`build_order_intent` inputs). The PreOrderRiskGate
  keeps its role as validator — its notional caps are absolute upper bounds
  the multiplier can never exceed.
- Composition with existing controls is **multiplicative**, and reduction
  always wins: `final = base_notional x sizing_tier x
  RISK_LEVEL_REDUCED_POSITION_MULTIPLIER (when reduced) `, then clamped by the
  gate caps.

### D5. Loss limits: add a currency limit alongside R limits

Variable per-trade risk makes `DAILY_MAX_LOSS_R = -2.0` a variable currency
amount. Keep the R limits AND add a paper-stage currency limit (mirroring the
live path's `LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT`), both enforced — whichever
trips first wins.

## Non-goals

- No sizing on the live path until the paper implementation has run through at
  least one full tier promotion + demotion cycle.
- No per-signal sizing (signals do not persist).
- No automatic tier promotion — D1 requires the operator intake.

## Implementation sketch (when picked up)

1. `feedback/`: sizing profile candidate builder (reads independent events per
   strategy + regime coverage; writes `sizing_profile_candidate.json`).
2. Operator intake validator (pattern-copy of the live-profile intake).
3. Bridge: read the APPROVED sizing profile (hash-pinned like the live
   profile), apply the tier multiplier before the gate.
4. Tests: tier resolution fail-closed matrix, cap clamping, reduction
   composition, and the "no approved profile -> everything base" default.
