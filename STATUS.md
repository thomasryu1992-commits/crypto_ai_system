# Crypto AI System — Status

_Single source of truth for current state. Historical phase/step reports live in `docs/history/`._

## Architecture

Five independent agents run as one loop. Each wraps existing core modules and
hands off via JSON under `storage/latest/`.

```
data → research → validation → trading → feedback
```

| Agent | Module | Wraps | Output |
|---|---|---|---|
| data | `crypto_ai_system.pipeline.data_agent` | collectors + builders | market context |
| research | `crypto_ai_system.pipeline.research_agent` | research_engine + decision_engine | research signal + decision |
| validation | `crypto_ai_system.pipeline.validation_agent` | data_health + risk_guard | `allow_new_position` gate |
| trading | `crypto_ai_system.pipeline.trading_agent` | bridge + trading_cycle + order_executor + reconciler | order result + reconciliation |
| feedback | `crypto_ai_system.pipeline.feedback_agent` | outcome_analytics + performance_report + candidate_profile | candidate (no runtime mutation) |

Orchestration: `crypto_ai_system.pipeline.orchestrator.Pipeline`.

### Fail-closed semantics
- Upstream ERROR / fatal BLOCK in data/research/validation → trading is SKIPPED (no orders on bad inputs).
- Validation no-trade verdict → trading runs in no-new-position mode (DEGRADED, not halt).
- Feedback runs every cycle, so no-trade cycles still produce learning.
- Live/testnet order paths are refused unless explicitly enabled **and** the confirmation phrase is set.

## Run

```bash
python run_pipeline.py            # one cycle, human-readable report
python run_pipeline.py --json     # machine-readable
python -m pytest -q               # tests
python scripts/check_safety_defaults.py   # fail-closed flag guard
```

### Sustained paper (scheduler)
```bash
py run_scheduler.py                       # run forever, one cycle / hour
py run_scheduler.py --interval 900        # every 15 min
py run_scheduler.py --cycles 24           # 24 cycles then stop
py run_scheduler.py --once                # single cycle
py scripts/paper_performance_summary.py   # accumulated expectancy/win/drawdown
```
Runs the pipeline on an interval to accumulate paper outcomes on real data
(no orders unless the signed-testnet path is explicitly enabled). Foreground;
Ctrl+C stops it.

### Durable scheduling (survives terminal/session close)
Register a Windows Scheduled Task that runs one cycle every hour:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1
powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1 -IntervalMinutes 60
powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1 -Remove   # unregister
```
Each run executes `run_scheduler.py --once` (via `scripts\run_scheduler_once.bat`),
appending to `storage\logs\scheduler.log` and the dashboard metrics log. Verify
with `Get-ScheduledTask -TaskName CryptoAISystemPaperScheduler`.

### Metrics dashboard
```bash
py scripts/dashboard.py            # status board: cycles, performance, warnings
py scripts/dashboard.py --json     # machine-readable
py scripts/dashboard.py --watch 30 # refresh every 30s
```
Reads the scheduler's per-cycle metrics log (`scheduler_metrics.jsonl`) plus the
latest performance report and shows uptime, trades placed, expectancy/win/
drawdown, and health warnings (negative expectancy, stale data, signal drift,
reconciliation mismatch, recent errors, synthetic data).

To start performance measurement from zero (e.g. after switching to real data),
clear the accumulated outcome/paper history — it is backed up first:
```bash
py scripts/reset_paper_outcomes.py            # dry run: show what would clear
py scripts/reset_paper_outcomes.py --confirm  # back up + clear (reversible)
```

## Current stage: signed testnet (order + reconciliation verified)

| Concern | State |
|---|---|
| Pipeline end-to-end | ✅ runs (all five stages OK on real data) |
| Data source | ✅ real Binance USD-M Futures public klines (read-only, no key); synthetic fallback on failure |
| Paper execution | ✅ works |
| Signed-testnet adapter | ✅ verified — one order submitted and FILLED on testnet (2026-07-15), reconciled with zero mismatches |
| Testnet reconciliation | ✅ verified — RECONCILED against a real testnet fill (order/position/balance matched intent) |
| Live canary order boundary | ✅ verified — one real mainnet order FILLED and RECONCILED (2026-07-16) |
| Live strategy (autonomous) path | ✅ implemented (L1–L6: P&L ledger + breaker, final guard, stage wiring, live gate/profile, position kernel, pipeline integration); **never enabled** — every flag fail-closed, needs promotion evidence |
| Live/testnet/canary/strategy flags | 🔒 all False by default (fail-closed; guarded by `check_safety_defaults.py`) |

## Path to live (3 gates, not 15 phases)

```
paper (real data)  →  signed testnet  →  live canary (fixed small size)  →  live
```

Each promotion is a single `config.settings` stage flag + a one-page checklist +
manual operator approval. Safety (kill switch, notional cap, daily-loss limit,
hot-path risk gate) is enforced in code, not in evidence artifacts.

### Next steps
1. ✅ Real market data wired (Binance public klines). Run paper on real data for a sustained window (schedule `run_pipeline.py`) and review outcomes.
2. ✅ Signed-testnet order adapter implemented (HMAC signing + POST) behind the existing contracts (idempotency, client order id, endpoint allowlist, hard caps, final guard). Disabled by default.
3. **Operator step**: create Binance **testnet** API keys, set env (`BINANCE_API_KEY/SECRET`, `TESTNET_SIGNED_ORDER_ENABLED=true`, `SIGNED_TESTNET_PLACE_ORDER_ENABLED=true`, `LIVE_TRADING_CONFIRMATION=I_UNDERSTAND_THIS_PLACES_REAL_ORDERS`), and submit one testnet order. Claude does not run this or handle real keys.
4. ✅ Testnet reconciliation implemented + verified (first order RECONCILED on testnet).
5. ✅ Repeated-session harness (Phase 10) — `run_testnet_session.py` runs N open/close cycles with fill/slippage/latency/cost stats. **Operator step**: run several sessions (raise the daily cap) to confirm stability.
6. ✅ Live canary preparation gate implemented (`scripts/check_live_canary_readiness.py`) — requires ≥5 clean testnet sessions plus a live **read-only** probe (key restrictions, balance, symbol filters, commission). GET-only by construction; grants no order authority. **Operator step**: run enough clean sessions, create a live read-only key (no withdrawals/transfers), then run the check with `--probe`.
7. ✅ Live canary one-order boundary implemented **and verified** — one real mainnet order FILLED and RECONCILED with zero mismatches (2026-07-16) via `run_live_canary_order.py`. Each reconciled canary order is recorded as promotion evidence (`live_canary_order_registry`).
8. ✅ Autonomous live strategy path implemented (L1–L6, disabled by default — see "Live strategy trading" below). **Operator steps to go live**: (a) accumulate ≥`LIVE_STRATEGY_MIN_CLEAN_CANARY_ORDERS` (default 3) clean canary orders; (b) set the full `LIVE_STRATEGY_*` env (separate order-capable key, its own confirmation phrase, caps, and a real daily-loss limit); (c) enable strategy routing+drive and run the scheduler. Claude does not run this or handle real keys.

### Live strategy trading (autonomous, L1–L6 — implemented, never enabled)
The pipeline can route its trading stage to `live`: a routed strategy candidate
builds a live decision through the PreOrderRiskGate (operator-approved live
profile + real live risk inputs), the approved gate result is persisted as a
stage=`live` RiskGate record, and the order flows decision → intent → the L2
final guard → the mainnet adapter, then reconciles. Layers (each fail-closed):

| Layer | Module | What it enforces |
|---|---|---|
| L1 P&L ledger | `execution/live_pnl_ledger.py` | realized live P&L (USDT); an **unconfigured daily-loss limit blocks** |
| L2 final guard | `execution/live_order_final_guard.py` | flags + distinct confirmation + kill switch + loss breaker + promotion gate + caps (order/daily/exposure, absolute ceiling) + **verified stage=live RiskGate record** |
| L3 wiring | `execution_port` / `live_strategy_execution.py` | stage routing; partial config refuses loudly (never silently downgrades) |
| L4 live gate | `research/live_profile.py` + bridge | operator-approved live profile (approval = complete env config); signal carries its hash; live gate fed real ledger/counter numbers |
| L5 position kernel | `execution/live_position_kernel.py` | real reduceOnly closes (SL/TP/time); fail-open-position (never fabricates a close); closes exempt from breaker/kill-switch (risk reduction) but not from the structural boundary |
| L6 integration | `pipeline/trading_agent.py` | settle-first, real exposure counting, kernel open on RECONCILED fills |

Required env (any missing one keeps the path fail-closed):
```
LIVE_STRATEGY_ORDER_ENABLED=true
LIVE_STRATEGY_PLACE_ORDER_ENABLED=true
LIVE_STRATEGY_CONFIRMATION=I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY
LIVE_STRATEGY_API_KEY=<order-capable live key, no withdraw/transfer>
LIVE_STRATEGY_API_SECRET=<...>
LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT=60      # <= absolute ceiling 200
LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT=2
LIVE_STRATEGY_MAX_OPEN_NOTIONAL_USDT=120
LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT=20        # circuit breaker; 0 blocks
```
Plus `STRATEGY_FACTORY_ROUTING_ENABLED` + `STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED`
(the strategies that trade) and ≥3 clean canary orders on record. Kill switch:
`LIVE_STRATEGY_MANUAL_KILL_SWITCH=true` halts new entries immediately (open
positions still close). The daily-loss breaker halts entries for the day once
today's realized live loss reaches the limit.

### Operator go-live checklist (real money — do NOT skip a step)

Work top to bottom on ONE machine (evidence lives in gitignored `storage/`). The
code is done and fail-closed; this is entirely operator judgement + real keys.
Claude does not run these or handle real secrets.

**Gate 0 — Earn confidence in the strategies (before any live money)**
- [ ] Paper on real data shows **positive expectancy** over a sustained window —
      `py scripts/paper_performance_summary.py` (don't go live on a negative edge).
- [ ] The active pool is populated with champions you trust —
      `py run_strategy_factory.py --status`.
- [ ] Testnet drive sanity: run the pipeline with routing+drive on testnet-scale
      and confirm strategy entries reconcile cleanly.

**Gate 1 — Preparation is READY** (from the canary section above)
- [ ] `py scripts/check_live_canary_readiness.py --probe` → `preparation READY`
      (≥5 clean testnet sessions + a live read-only probe).

**Gate 2 — Promotion evidence: ≥3 clean live-canary orders**
- [ ] Place canary orders until 3 are clean (each reconciled canary is
      auto-recorded): `py run_live_canary_order.py --confirm` (daily cap 1, so
      across ≥3 days or raise `LIVE_CANARY_MAX_DAILY_ORDER_COUNT`). **Close each
      canary position on the venue** afterwards — canaries only open.
- [ ] Verify the count: the `live_canary_order_registry` holds ≥3 `clean: true`
      rows (or just proceed — the final guard blocks if short).

**Gate 3 — Configure the live-strategy boundary (conservative first)**
- [ ] Create a SEPARATE order-capable live key: enable Futures, **disable
      withdrawals + internal transfer**, ideally IP-whitelisted. Keep it distinct
      from the read-only probe key and the canary key.
- [ ] Set the full `LIVE_STRATEGY_*` env (above). Start SMALL:
      `MAX_ORDER_NOTIONAL_USDT` near the venue minimum (~65), `MAX_DAILY_ORDER_COUNT=1`,
      `MAX_OPEN_NOTIONAL_USDT` = one position, `DAILY_LOSS_LIMIT_USDT` low (e.g. 20).
- [ ] Enable `STRATEGY_FACTORY_ROUTING_ENABLED` + `STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED`.

**Gate 4 — Dry-verify the gate before any autonomous run**
- [ ] `py scripts/check_safety_defaults.py` now FAILS (expected — you enabled live).
- [ ] Run ONE pipeline cycle and confirm the trading stage resolves to `live`
      (not a refusal): `py run_pipeline.py` — a refusal message means a missing
      piece; fix it before continuing.

**Gate 5 — First supervised live cycles**
- [ ] Run the scheduler and **watch the first entries/closes live** —
      `py run_scheduler.py --interval 900` (or `--once` a few times). Confirm each
      live entry reconciles and the position closes on SL/TP/time.
- [ ] Watch `storage/latest/live_risk_status.json` (today's realized P&L) and the
      dashboard; confirm the daily-loss breaker and open-exposure cap behave.

**Standing controls (know these cold before you start)**
- **Stop new entries now:** set `LIVE_STRATEGY_MANUAL_KILL_SWITCH=true` (open
  positions keep closing) — or unset any `LIVE_STRATEGY_*` flag.
- **Daily-loss breaker:** entries halt for the UTC day once realized live loss
  reaches `LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT`; resumes next UTC day.
- **A stuck position** (close blocked/unconfirmed) stays OPEN and is retried each
  cycle — you can always flatten manually on the venue; that never depends on
  this code.
- Raise caps only after several clean, profitable live days.

### Enabling the signed-testnet path (operator, on a testnet account only)
Create Binance USD-M **Futures testnet** API keys at
https://testnet.binancefuture.com. All of these must be set — any one missing
keeps the path fail-closed:
```
BINANCE_API_KEY=<testnet key>
BINANCE_API_SECRET=<testnet secret>
BINANCE_TESTNET=true
TESTNET_SIGNED_ORDER_ENABLED=true
SIGNED_TESTNET_PLACE_ORDER_ENABLED=true
LIVE_TRADING_CONFIRMATION=I_UNDERSTAND_THIS_PLACES_REAL_ORDERS
SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT=150   # see note below
```
Hard caps still apply: `SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT` (default 5) and
`SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT` (default 3). The pre-submit final guard
(`execution/signed_testnet_final_guard.py`) re-checks all of this before signing.

> **Min-notional note:** Binance USD-M Futures BTCUSDT has a minimum order
> notional of ~100 USDT (min qty 0.001 BTC). The default cap of 5 USDT is too
> low to place a real order — raise `SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT` to
> ~150. This is testnet (fake) money.

### Verifying a single testnet order (operator)
```
py scripts/check_testnet_readiness.py --probe   # config + signed read-only auth probe (no order)
py run_testnet_order.py                          # dry preflight only
py run_testnet_order.py --confirm                # place ONE small order, then reconcile
```
The runner sizes one order within the cap, submits it through the final guard
and adapter, then prints the fill/position/balance reconciliation. Claude does
not run this — it is an operator action with real testnet keys.

### Repeated sessions (Phase 10, operator)
```
py run_testnet_session.py --sessions 3 --confirm   # N open/close cycles + stats
```
Each session opens a small long and closes it (reduceOnly), reconciling each
leg, and reports fill/reconcile rate, slippage (bps), latency (ms), and
round-trip cost. It stops early when the daily order cap is hit. Each session
uses 2 orders, so `--sessions` is bounded by
`SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT / 2` — raise the daily cap for longer runs
(testnet fake funds).

### Live canary preparation (operator)
```
py scripts/check_live_canary_readiness.py           # testnet evidence + config only
py scripts/check_live_canary_readiness.py --probe   # + signed GET-only live probe
```
Gate 1 needs `storage/latest/signed_testnet_session_report.json` with ≥5 clean,
fully reconciled sessions. Gate 2 needs `LIVE_READONLY_PROBE_ENABLED=true` and a
**separate live API key restricted to reading** (`LIVE_BINANCE_API_KEY/SECRET`);
the probe fails closed if the key allows withdrawals or transfers. The written
report (`storage/latest/live_canary_preparation.json`) is evidence only — every
order-authority flag in it is hardcoded false, and the live canary order itself
remains a separate approval and runtime boundary.

### Live canary order (operator — places ONE real mainnet order)
Only after the preparation report is READY. This is a separate boundary from the
pipeline (which still refuses live) and uses a **different** key and confirmation
phrase than testnet, so nothing about the testnet path can authorize it.
```
py run_live_canary_order.py             # dry preflight: shows the guard verdict, no order
py run_live_canary_order.py --confirm   # place ONE real order + reconcile
```
All fail-closed; every one of these must be set (any missing one blocks):
```
LIVE_CANARY_ENABLED=true
LIVE_CANARY_PLACE_ORDER_ENABLED=true
LIVE_CANARY_CONFIRMATION=I_UNDERSTAND_THIS_PLACES_A_REAL_LIVE_MAINNET_ORDER
LIVE_CANARY_API_KEY=<order-capable live key, no withdraw/transfer>
LIVE_CANARY_API_SECRET=<...>
LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT=150   # BTCUSDT min notional ~100; <= absolute ceiling 200
```
The final guard (`execution/live_canary_final_guard.py`) re-checks all of this
before signing: enable flags, the distinct confirmation, the kill switch
(`LIVE_CANARY_MANUAL_KILL_SWITCH`), a mainnet-host allowlist, the configured cap
bounded by `LIVE_CANARY_ABSOLUTE_MAX_NOTIONAL_USDT` (200), a single-order daily
cap (`LIVE_CANARY_MAX_DAILY_ORDER_COUNT`, default 1), and that
`live_canary_preparation.json` is READY. Use a **separate** order-capable key
from the read-only probe key. Claude does not run this or handle real keys.

## Strategy Factory (continuous strategy production → selection → retirement)

A second, independent track that layers a multi-strategy ecosystem onto the same
5-agent runtime: strategies are generated continuously, backtested in batches,
the best are promoted into an active pool that trades with `OR` semantics behind
the shared research/risk gates, and strategies whose live performance decays are
auto-suspended. It never bypasses `PreOrderRiskGate`, never auto-promotes to
testnet/live, and never auto-reactivates a suspended strategy. Design doc:
`Crypto_AI_System_Independent_Agent_Strategy_Factory_Architecture...` (2026-07-15).

Roadmap S1–S11:

| Phase | Scope | State |
|---|---|---|
| S1 | Strategy contract foundation: `StrategySpec`, status model, rule hash, allowed-feature registry, candidate registry | ✅ done (`src/crypto_ai_system/strategy_factory/`) |
| S2 | Generation batches (4 specs/gen) from template + parameter mutation | ✅ done — 6 templates spanning long/short × trend/breakout/range (`strategy_template_library`) |
| S3 | Validation agent (feature-exists / look-ahead / stop-loss / ranges) | ✅ done (`strategy_validator_agent`) |
| S4 | Unified backtest engine (cost + slippage + walk-forward + regime split) — critical path, split S4a–S4e | ✅ done (`backtesting/`) |
| ├ S4a | Spec evaluator (feature row → entry match/direction; shared with S7) | ✅ done (`strategy_evaluator`) |
| ├ S4b | Cost + slippage + position-sizing model | ✅ done (`cost_model`) |
| ├ S4c | Execution simulator (single in-sample pass → trade ledger) | ✅ done (`execution_simulator`) |
| ├ S4d | Performance metrics (expectancy_R, profit_factor, drawdown, sharpe-like…) | ✅ done (`performance_metrics`) |
| └ S4e | Walk-forward + regime split + BacktestAgent record | ✅ done (`backtest_agent`) |
| S5 | Batch champion selection (relative rank **and** absolute gate) | ✅ done (`champion_selector_agent`) |
| S6 | Active strategy pool (paper cap 5, status model) | ✅ done (`active_strategy_pool`) |
| S7 | Multi-strategy entry router (`OR`, direction-conflict block) | ✅ router + shadow + paper-drive wiring done (opt-in, gated) |
| S8 | Strategy-id outcome attribution | ✅ done (`strategy_outcome_attribution`) |
| S9–S10 | Rolling performance + lifecycle (Warning→Probation→Suspend→Archive) | ✅ done (`feedback/strategy_performance_agent`, `feedback/strategy_lifecycle_agent`) |
| S11 | Continuous factory loop + diversity guard | ✅ done (`continuous_factory`); runner `run_strategy_factory.py` populates the pool |

A strategy spec is declarative data, never generated code: `can_submit_orders`
and `can_modify_runtime` are hardcoded false and a spec that tries to set them is
rejected. The allowed-feature registry tracks the *real* `feature_store` columns,
so a spec cannot reference a feature that will not exist at evaluation time.

The full offline factory (S1–S11) is complete: `continuous_factory.run_factory_cycle`
runs generate → backtest → champion → pool per generation, the lifecycle agent
retires decayed strategies, and the router turns the active pool into entry
candidates.

**Live wiring — increment 1 (shadow):** behind `STRATEGY_FACTORY_ROUTING_ENABLED`
(default false, in the fail-closed safety guard), the pipeline runs a
`StrategyRoutingAgent` after validation. It rebuilds the full feature row from
the live candles via the same `build_feature_frame` the backtest uses
(`runtime_feature_adapter`), routes the active pool over it, and writes
`storage/latest/strategy_routing.json`. It is advisory — `drives_execution=false`,
never halts the pipeline, and the default pipeline is unchanged when the flag is
off.

**Live wiring — increment 2 (paper drive):** behind
`STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED` (default false, in the safety guard;
requires routing enabled too, paper stage only). When a routed candidate exists,
`strategy_execution_bridge` assembles a canonical trade decision — direction from
the strategy, entry from the live price, SL/TP from the strategy's ATR exit rules,
plus S8 attribution — and evaluates a fresh PreOrderRiskGate for that direction.
Following §2.2, the strategy only creates the opportunity: `allow_order_intent`
is true only when the research permission allows the direction **and** the gate
approves; otherwise the research decision stands (fail-closed). When it is
approved the *unchanged* order executor + paper kernel carry it, and the S8
attribution (strategy_id / eval id / rule hash) rides the order intent → paper
position → outcome. Verified on real artifacts: the decision assembles correctly
and refuses order intent when the gate/permission don't approve.

**Live wiring — increment 3 (closed loop):** when a strategy-driven paper
position closes, the trading agent records an S8-attributed outcome
(`strategy_feedback_step.record_strategy_outcome`) to the attributed-outcome
registry; research-driven closes are skipped. Each feedback cycle then recomputes
S9 rolling performance per active strategy and applies the S10 lifecycle decision
to the pool (`run_strategy_lifecycle_feedback`) — a decayed strategy escalates
WARNING → PROBATION → SUSPENDED, and once suspended the router stops routing it.
Both halves are gated by the routing flag and isolated (best-effort, never break
the trade path). Verified end-to-end: 50 losing paper trades drive a strategy to
SUSPENDED and the router excludes it. **The factory loop is now closed on real
paper trades** — production → selection → operation → retirement runs
automatically; testnet/live promotion and reactivation stay manual.

### Running the factory (operator)
```
py run_strategy_factory.py --history 1500 --cycles 6   # generate + backtest + populate the pool
py run_strategy_factory.py --status                    # show the current pool
```
This is the entry point that *fills* the active pool — the router/drive/lifecycle
only read it. Each cycle generates a batch, backtests on real candles, and adds at
most one champion to the paper pool (counters persist across runs). Every pool
decision (add / replace / reject) is appended to the append-only
`active_strategy_registry` audit trail. `--history N` fetches N recent klines
(≈200 cached bars is too few to clear the trade-count gate; 1500 real BTC bars
yields a qualifying trend-pullback champion). The absolute gate defaults are
tuned to short history: `--min-trades` below the directive floor (100) prints a
loud PROVISIONAL warning — a champion cleared on a thin sample is not yet
statistically trustworthy. To run the live paper loop end to end: populate the
pool with this runner, then enable `STRATEGY_FACTORY_ROUTING_ENABLED` (shadow)
and, once confident, `STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED` (paper drive).

Feature availability: all six shipped templates (trend/breakout/range × long/short)
use only price-derived columns, so they trade on the runtime feature row. The
derivative/liquidation/multi-timeframe columns exist in the schema but are a
constant fallback without their feeds, so the S3 validator now rejects any spec
referencing them (`BLOCK_RUNTIME_UNAVAILABLE_FEATURE`) — no silently-degenerate
strategies. Wire a real feed and drop the name from
`allowed_feature_registry.RUNTIME_UNAVAILABLE_FEATURES` to unlock those columns.

### Scheduling the factory (operator, optional)
```
powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1                    # daily
powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1 -IntervalMinutes 10080  # weekly
powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1 -Remove
```
Registers a Windows Scheduled Task (`CryptoAISystemStrategyFactory`) that runs one
generation on an interval (directive §15: weekly→daily), logging to
`storage\logs\strategy_factory.log`. Paper pool only — no testnet/live promotion.

### Integration run — verified end to end
Ran the real pipeline with routing enabled: all six stages run (data → research →
validation → **strategy_routing** → trading → feedback), the router evaluates the
live pool on the real feature row, and the common gates (validation risk guard,
research permission, PreOrderRiskGate) enforce as designed. The drive money-path
was verified through the real order path: a strategy decision → order executor →
paper fill → position (carrying `strategy_id`) → settle → attributed outcome →
S9 aggregation. This run surfaced and fixed a real gap — the strategy decision now
carries the `decision_id` / `research_signal_id` / `profile_id` lineage the paper
engine requires (it rejected the intent without them).

### Multi-regime template library
The template library spans the three regimes in both directions — trend
(`trend_pullback` / `trend_pullback_short`), breakout (`breakout` /
`breakdown_short`), and range (`mean_reversion` / `mean_reversion_short`) — all on
real `feature_store` columns (breakout is now price-based, no derivatives feed
needed). The backtest decides what qualifies per market: on real BTC uptrend
history only `trend_pullback` (long) qualifies, while on a downtrend the two short
families qualify — so the pool adapts to market direction as the factory runs.
A strategy still trades only when the common research permission allows its
direction (§2.2), so range/counter-trend entries also depend on that gate.

## Maintenance

**2026-07-19 — QA audit fixes (fail-closed hardening).** A full-structure QA
audit surfaced gaps where uncertainty resolved in the optimistic direction;
all fixed, no safety default changed, verified with the full suite (847),
`check_safety_defaults.py`, and a live pipeline cycle:

- **Strategy drive now consumes the validation verdicts.** `data_health.allow_trading`
  and `risk.allow_new_position` are REQUIRED inputs to `build_strategy_trade_decision`
  (new block reasons `DATA_HEALTH_DISALLOWS_TRADING` / `RISK_GUARD_DISALLOWS_NEW_POSITION`);
  the strategy gate also gets the settings-derived loss limits the research bridge passes.
- **DATA_FRESHNESS gate un-deadened.** `market_snapshot` now computes `is_stale`
  (same `MAX_STALE_DATA_MINUTES` threshold as data_health), so the PreOrderRiskGate's
  freshness check has a real input.
- **Ambiguous submits are resolved, never assumed away.** A timeout/5xx after the
  POST left the process queries the venue by client order id
  (`retry_policy.resolve_ambiguous_submit`); unresolved counts as possibly-live
  (daily budget + reconciliation). Applied to live-strategy entry/close and the
  signed-testnet port.
- **Unconfirmed closes re-queried under the SAME client order id.** The live
  position kernel persists the close id write-ahead; a later fill is realized into
  the L1 ledger (daily-loss breaker sees it), and only a venue-confirmed dead
  order allows a fresh close.
- **Kill switch no longer strands an open live position.** The trading agent
  settles the open live position (SL/TP/time via the close guard, which exempts
  reduceOnly closes) BEFORE refusing a blocked live stage.
- **Risk guard fails closed on unreadable history.** The legacy
  `paper_trades.json` fallback is gone: an unreadable outcome registry now
  yields `BLOCK_NEW_POSITION` (`risk_history_unreadable`), never silent zero history.
- **Drawdown breaker acts on CURRENT drawdown** (unlatches on recovery) with the
  principled mapping `MAX_DRAWDOWN_PCT / RISK_PER_TRADE` (default -10% / 1% = 10R);
  historical max is reported separately.
- **Single-runner lock.** `core/run_lock.py` (OS file lock, dies with the process)
  stops a scheduled task and a manual run from interleaving `storage/latest/`
  artifacts; exit code 40 = skipped, lock held.
- **`check_safety_defaults.py` hardened**: covers all order-path enable flags,
  asserts guard-rail flags stay True, and FAILS on renamed/deleted flags instead
  of passing vacuously.
- **Forming candle dropped at collection** (`drop_forming_candle`): every
  consumer (snapshot, health, settlement, research) sees only CLOSED bars — no
  indicator repaint, no SL/TP on partial-bar extremes.
- Advisory-stage ERRORs (fatal_on_error=False) no longer exit as an error halt.

**2026-07-16 — lean-debt cleanup (PR #19, merged to `main`).** An audit-driven
sweep of the post-refactor codebase. No safety default changed, no order path
enabled; verified each step with the full suite, `check_safety_defaults.py`, and a
live pipeline cycle. Test count 525 → 501 (legacy tests removed, new tests added
for the guards/wiring below).

- **Dead code removed.** Ghost `.pyc`-only packages (`governance`, `agents`,
  `validation`, `ops`, `reports`) and the two entry points that `ImportError`ed
  against them; dead root twins (`market_context_builder`, `market_snapshot_builder`,
  `real_market_data_collector`), legacy `risk/risk_manager.py`, the `DISABLED_STUB`
  `research_signal_profile_*` chain, and the `step209_237` runner.
- **Legacy paper-simulation subsystem removed.** The whole `backtest/` package (a
  closed import cluster reachable only from legacy step tests, superseded by the
  v2/kernel path): `engine`, `metrics`, `parameter_sweep`, `paper_observation_queue`,
  `paper_signal_replay`, `paper_trading_candidate_registry`, `strategy_matrix_execution`,
  plus `execution/paper_execution_dry_run_bridge`, `execution/simulated_paper_order_lifecycle`,
  `feedback/paper_lifecycle_outcome_store`. Ends the `backtest`/`backtesting` name
  collision; `order_id_chain.chain_complete` stays covered by the v2 tests.
- **Config unified.** `src/crypto_ai_system/config.py` now seeds the research-signal
  gate and safety flags from the flat `config.settings` constants, so a `settings.yaml`
  value can no longer silently diverge from the flat half and split gate semantics.
- **Fail-visible IO.** `core.json_io.read_json` logs a WARNING when an existing file
  fails to parse (was silently swallowed); closed-loop best-effort catches (strategy
  attribution, S9/S10 lifecycle) `log_event` on failure instead of `pass`.
- **§10 audit registries wired.** `factory_runner` now appends every pool decision
  to `active_strategy_registry` and every generated candidate spec to
  `strategy_candidate_registry` (both were code-present but never written).
- **Feature contract honesty.** Derivative/liquidation/multi-timeframe columns are a
  constant fallback without their feeds, so the S3 validator rejects any spec
  referencing them (`BLOCK_RUNTIME_UNAVAILABLE_FEATURE`).
- **`storage/latest/` pruned** 436 → 53 files; frozen pre-refactor artifacts moved to
  `storage/archive/pre-lean/` (gitignored).

## History

Pre-refactor state (the over-engineered governance/evidence apparatus) is frozen
at tag/branch `archive/pre-lean-2026-07-15`. Development reports are in `docs/history/`.
