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
| Live order path | ❌ not implemented; trading agent refuses it |
| Live/testnet flags | 🔒 all False by default (fail-closed) |

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
7. Live canary one-order boundary (separate approval + runtime, after step 6 is READY).

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
| S2 | Generation batches (4 specs/gen) from template + parameter mutation | ✅ done (`strategy_generator_agent`, `strategy_template_library`) |
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
| S11 | Continuous factory loop + diversity guard | ✅ done (`continuous_factory`) |

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
and refuses order intent when the gate/permission don't approve. **Remaining:**
consume the attributed paper outcomes into S9/S10 live (close the factory loop on
real paper trades).

## History

Pre-refactor state (the over-engineered governance/evidence apparatus) is frozen
at tag/branch `archive/pre-lean-2026-07-15`. Development reports are in `docs/history/`.
