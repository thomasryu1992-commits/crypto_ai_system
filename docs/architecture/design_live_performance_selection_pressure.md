# Design: live (paper) performance as breeding selection pressure

_Status: L-A IMPLEMENTED (2026-07-20, branch
`feat/live-performance-selection-pressure`); L-B deferred until live data
exists to validate against, as planned._

**[as-built] notes.** `live_evidence.py` carries SLS + per-strategy stats +
the IO loader (best-effort by design: an unreadable S8 registry means no
pressure, not a blocked run — nothing here authorizes trading, contrast
risk_guard). L-A1 landed in `add_champion` via an optional `live_stats`
param injected at the IO boundaries (`factory_runner.run_generation`,
`run_rule_miner`); `continuous_factory.run_factory_cycle` stays pure and
passes it through. Decision rows carry the audit fields (`weakest_live_n`,
`weakest_live_expectancy`, `weakest_frozen_score`, `sls_pseudo_trades`).
L-A2 landed as `seed_weights` on `mine_rule_sets`: caller sorts seeds by SLS
(truncation keeps live-best) and weights `1+w` bias crossover-parent choice
in the first breeding round only; `seed_weights=None` keeps the exact
original rng consumption (byte-identical searches). K =
`STRATEGY_LIVE_PRESSURE_PSEUDO_TRADES` (settings, default 20)._

## Problem

Real trading results currently influence breeding only through **occupancy**:
a strategy that decays gets SUSPENDED (S10) and thereby stops seeding the
miner. That signal is binary and slow — suspension needs two consecutive
failing evaluations over FULL rolling windows (20–50 trades each), which at
the pool's current trade rate is months away for most strategies. Meanwhile:

- `champion_score` is **frozen at pool admission** (full-frame backtest
  expectancy). An incumbent whose live record refutes its backtest resists
  displacement in `add_champion` exactly as strongly as one whose live record
  confirms it.
- Every occupying champion seeds the miner's initial population with **equal
  standing** — one lottery ticket each, regardless of live evidence.
- The miner's fitness is a train-slice t-statistic; live results never touch
  selection, crossover, or admission.

So between "fully trusted" (occupying) and "expelled" (suspended) there is no
graded pressure from reality. The request: make real results push, not just
evict.

## The honest constraint: sample sizes

Pool-wide paper throughput is ~1–2 entries/day (1d-regime strategies gated by
research permission + book caps). Per-strategy live samples will be
**single-digit for months**; the S8 attributed registry holds a handful of
rows today. Backtest evidence rests on 100+ trades per strategy.

Any design that lets a 3-trade live sample move scores materially is a
noise amplifier, not selection pressure. The design principle is therefore:

> **Live evidence enters only through sample-size-aware shrinkage, so that
> zero/thin data reproduces current behavior exactly, and influence grows in
> proportion to information content.**

This also gives a free rollout property: the mechanism can ship enabled and
is a mathematical no-op until real data accumulates.

## What live data uniquely knows (and backtests cannot)

1. **Execution reality** — actual fills, slippage, and costs, not the cost
   model's assumptions.
2. **Runtime feature parity** — whether the live feature row really behaves
   like the backtest frame's (the S3 runtime-unavailable guard catches the
   binary case; live results catch the subtle ones).
3. **Regime-now** — the backtest's holdout ends where history ended; live
   trades sample the only regime that pays.
4. **Surviving overfit** — a rule that beat the 30% holdout by luck gets one
   more, truly independent referee.

Note what live data is NOT: an independent market-data sample large enough to
compute fitness on. It is a thin, high-value **correction term**.

## Core mechanism: the shrunk live-blended score (SLS)

For strategy *i* with `n_i` attributed live outcomes (S8 registry), live
expectancy `live_i`, and admission backtest expectancy `bt_i`
(= `champion_score`):

```
w_i   = n_i / (n_i + K)              # K = pseudo-trade count, default 20
SLS_i = w_i * live_i + (1 - w_i) * bt_i
```

- `n=0`  → `SLS = bt` — **exactly current behavior**.
- `n=5`  → live carries 20%.
- `n=20` → 50/50.
- `n=60` → live carries 75%; the backtest becomes the prior it should be.

`K` is one tunable (`STRATEGY_LIVE_PRESSURE_PSEUDO_TRADES`, settings, default
20). Implementation: one small pure module,
`strategy_factory/live_evidence.py`, reading the S8 attributed-outcome
registry + pool entries; unit-testable without IO via injected rows.

## Injection points (phased)

### L-A1 — Replacement pressure in the pool (highest value, do first)

`add_champion` currently finds the weakest occupant by frozen
`champion_score` and displaces it only if the challenger beats it by
`min_improvement`. Change: **rank occupants by SLS** at comparison time
(challenger has `n=0`, so its side is unchanged — pure backtest score).

Effect: a live-refuted incumbent's effective score sinks toward its real
record and it becomes progressively easier to displace; a live-confirmed
incumbent becomes harder to displace. The pool IS the parent set, so this is
already breeding pressure — parents are whoever survives here.

- `min_improvement` margin and the suspended-not-deleted rule are unchanged.
- The pool decision audit row records the SLS inputs
  (`live_n`, `live_expectancy`, `K`, blended score) so every displacement is
  explainable.

### L-A2 — Seed weighting in the miner

Seeding currently takes every expressible occupying champion, order
arbitrary, truncated at `population`. Change:

1. **Sort seeds by SLS descending** — when seeds exceed the population
   budget, the live-best survive truncation (today it is positional luck).
2. **Duplicate the top tercile** (2 copies each, still within the population
   budget) — live-validated genes get proportionally more crossover lottery
   tickets. Duplicates are deduped by the existing rule-set key only if
   identical, which they are — so implement as *selection weight*: elite
   sampling in generation 0 draws seeds with weight `1 + w_i` instead of
   literal copies.

No one who occupies is excluded (that stays S10's job); the pressure is
graded, bounded, and vanishes at `n=0`.

### L-B — Family-level fitness prior in the miner (later, flagged)

Per-strategy samples are thinnest; **family** samples (all attributed
outcomes across strategies sharing a `mined:`/template family) accumulate
faster. Compute per-family live divergence:

```
d_f = shrink(live_exp_f - bt_exp_f, n_f, K_f)      # K_f default 10
mult_f = 1 + clamp(d_f, -0.20, +0.20)
fitness'(candidate) = fitness(candidate) * mult_f   # f = candidate's family
```

Applies only when `n_f >= 10`; bounded to ±20% so backtest evidence always
dominates; the train-slice honesty contract is untouched (thresholds,
selection data, and the base fitness still see only the train slice — the
prior is a separate, recorded multiplicative term, exactly like
`search_evaluations` is a recorded denominator).

Flagged `STRATEGY_FAMILY_LIVE_PRIOR_ENABLED` (default False) because it
touches the fitness function; L-A1/L-A2 need no flag — shrinkage makes them
no-ops until data exists. (No `check_safety_defaults` entry: this is
paper-pool machinery, not an order path.)

## Explicitly rejected

- **Live R as a fitness dataset.** 0–5 trades cannot rank 480 candidates;
  and children are new strategies with zero live history — only ancestors
  have records, and crossover deliberately scrambles what "descends from"
  means at the individual level. Family-level (L-B) is the honest resolution.
- **Unbounded penalties or hard eviction from live data.** Retirement stays
  S10's ladder (2 consecutive full failing windows). SLS pressure is graded;
  making it terminal would double-jeopardize the same thin sample.
- **Updating `champion_score` in place.** The admission score is historical
  fact and audit anchor; SLS is computed at comparison time from current
  live evidence, never written over the original.
- **Letting live data into threshold/percentile selection.** The miner's
  train-slice contract stays byte-identical.

## Feedback-loop safety

The same attributed outcomes now feed S9→S10 (retirement) and SLS
(replacement/seeding). Bounded interactions:

- S10 unchanged — worst case a strategy is displaced by SLS before S10 would
  have suspended it; it is suspended-not-deleted either way and reactivation
  stays manual.
- A displaced-by-SLS strategy leaves seeding the same way a suspended one
  does — no new mechanism.
- SLS cannot admit anyone: admission gates (S3/holdout/absolute/diversity)
  are untouched. Pressure only reorders survivors.

## Expected effect timeline (honest)

At current throughput the busiest strategies reach `n≈5` (w=0.2) in roughly a
month. This design is a slow rudder by construction — anything faster would
be chasing noise on 1d strategies. The lever that shortens the timeline is
throughput (more books / more symbols), not a smaller K.

## Implementation order

1. `live_evidence.py` (pure SLS + family aggregation) + unit tests.
2. L-A1: `add_champion` comparison via SLS + audit fields + tests
   (thin-sample no-op test REQUIRED: n=0 pool behaves byte-identically).
3. L-A2: seed sort + weighted generation-0 sampling + tests.
4. L-B behind its flag, after L-A has real data to validate against.

Estimated: L-A one session; L-B a half session once wanted.
