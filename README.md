# Crypto AI System

A lean, agent-based crypto trading pipeline. Five independent agents run as one
loop, each wrapping focused core logic and handing off via JSON under
`storage/latest/`:

```
data → research → validation → [strategy_routing] → trading → feedback
```

- **data** — collect real market data (Binance USD-M public klines, closed bars
  only), build snapshot + context
- **research** — transparent research signal + research-level decision
- **validation** — data-health + risk-guard gate, emitted as a typed
  `ValidationVerdict` every decision builder must consume
- **strategy_routing** *(opt-in)* — evaluate the active strategy pool on the
  live feature row; a routed candidate can drive a paper entry
- **trading** — decision bridge → order executor → reconcile → position kernel
  (single-book or multibook paper)
- **feedback** — outcome analytics → performance report → strategy lifecycle

The loop is **fail-closed**: bad inputs skip trading, a no-trade verdict runs
trading in no-new-position mode, feedback always runs, and any live/testnet
order path is refused unless explicitly enabled with a confirmation phrase.
`scripts/check_safety_defaults.py` (CI-enforced) asserts every order-path flag
ships disabled. Uncertainty resolves conservatively: ambiguous order submits
are settled by querying the venue, unconfirmed closes re-query the same client
order id, and one persisted decision authorizes at most one order intent.

## Strategy Factory (second track)

A continuous strategy ecosystem layered on the same runtime: template
generation + rule mining → walk-forward backtest with cost model and holdout →
champion selection into a capped active pool → multibook paper trading with
S8 per-strategy outcome attribution → rolling-performance lifecycle
(WARNING → PROBATION → SUSPENDED). Real paper results feed back into breeding
as graded selection pressure (shrunk live-blended score — no-op until samples
accumulate, influence grows with evidence). Strategy specs are declarative
data, never generated code, and every entry still passes the shared research
permission + PreOrderRiskGate.

## Quick start

```bash
py run_pipeline.py                       # one cycle (use py, not python, on Windows)
py run_pipeline.py --json                # machine-readable
py run_scheduler.py --interval 900       # sustained paper loop (foreground)
py scripts/dashboard.py                  # cycles, performance, warnings
py scripts/paper_performance_summary.py  # accumulated expectancy/win/drawdown
py run_strategy_factory.py --status      # the active strategy pool
py -m pytest -q                          # test suite (network-free)
py scripts/check_safety_defaults.py      # fail-closed flag guard (must pass)
```

Durable scheduling (Windows Task Scheduler) and the operator runbooks for the
signed-testnet / live-canary boundaries are documented in
[STATUS.md](STATUS.md).

## Contracts

- Stage results and the typed cycle context: `crypto_ai_system.pipeline.contracts`
- The `storage/latest/` files are the inter-module API; core artifacts have
  typed views in `crypto_ai_system.artifacts` (writers stamp `schema_version`)
- Flat runtime constants live in `config/settings.py` and seed the structured
  `AppConfig` half — one resolution point per value

## Status & docs

See [STATUS.md](STATUS.md) for the current stage (paper on real data; signed
testnet and a live canary order each verified once, live strategy path
implemented but never enabled), the operator go-live checklist, and dated
maintenance notes for every change batch. Design documents live in
`docs/architecture/` (recent: the trading-agent decomposition and the
live-performance selection-pressure design, both with as-built notes).
Historical development reports are in `docs/history/`; the pre-refactor
codebase is frozen at `archive/pre-lean-2026-07-15`.
