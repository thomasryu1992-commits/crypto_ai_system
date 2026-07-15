# Crypto AI System

A lean, agent-based crypto trading pipeline. Five independent agents run as one
loop, each wrapping focused core logic and handing off via JSON under
`storage/latest/`:

```
data → research → validation → trading → feedback
```

- **data** — collect market data, build snapshot + context
- **research** — transparent research signal + research-level decision
- **validation** — data-health + risk-guard gate (`allow_new_position`)
- **trading** — decision bridge → trading cycle → execution → reconcile
- **feedback** — outcome analytics → performance report → candidate profile

The loop is **fail-closed**: bad inputs skip trading, a no-trade verdict runs
trading in no-new-position mode, feedback always runs, and any live/testnet
order path is refused unless explicitly enabled with a confirmation phrase.

## Quick start

```bash
python run_pipeline.py            # run one cycle
python run_pipeline.py --json     # machine-readable output
python -m pytest -q               # tests
```

## Status & roadmap

See [STATUS.md](STATUS.md) for the current stage (paper / pre-live), the
architecture table, and the path to live. Historical development reports are in
`docs/history/`; the pre-refactor codebase is frozen at
`archive/pre-lean-2026-07-15`.
