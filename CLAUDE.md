# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. Keep this file
current; it is the shared contract across machines.

## What this is

A lean, agent-based crypto trading pipeline. Five independent agents run as one
loop, each wrapping focused core logic and handing off via JSON under
`storage/latest/`:

```
data → research → validation → trading → feedback
```

The system was refactored down from a ~1,200-file governance/evidence apparatus
to ~230 functional files. The pre-refactor codebase is frozen at the git
tag/branch `archive/pre-lean-2026-07-15`. Historical reports live in `docs/history/`.

See `STATUS.md` for current stage and the path to live. **Read `STATUS.md` at the
start of a session** — it is the single source of truth for what is done.

## Environment

- **Windows** (primary dev machine). Shell examples assume Git Bash or PowerShell.
- **Python**: use the `py` launcher (`py run_pipeline.py`), not `python` — the
  bare `python` on Windows may be the Store stub. CI uses Python 3.11; local dev
  has been run on 3.14. Target 3.11 semantics.
- `PYTHONPATH` must include both `src` and the repo root (`src:.`). `run_pipeline.py`
  and the tests bootstrap this automatically; scripts set it via `pytest.ini`.

## Commands

```bash
py run_pipeline.py                       # run one trading cycle (human-readable)
py run_pipeline.py --json                # machine-readable
py -m pytest -q                          # full test suite
py -m pytest tests/test_pipeline.py -q   # pipeline tests only
py scripts/check_safety_defaults.py      # fail-closed flag guard (must pass)
py reset_paper_state.py                  # reset paper trading state
```

Data reset note: closed paper outcomes now live in the `outcome_feedback_registry`
(the paper position kernel is the single source), and `risk/risk_guard.py` reads
risk history from there — clearing `storage/latest/paper_trades.json` no longer
resets it. To start risk/performance history from zero (e.g. after switching data
sources), use `py scripts/reset_paper_outcomes.py --confirm` (backs up first).

## Architecture

| Agent | Module (`src/crypto_ai_system/pipeline/`) | Wraps |
|---|---|---|
| data | `data_agent.py` | `collectors/` + `builders/` |
| research | `research_agent.py` | `research.research_engine` + `research.decision_engine` |
| validation | `validation_agent.py` | `data_health.health_check` + `risk.risk_guard` |
| trading | `trading_agent.py` | `bridge.research_trading_bridge` + `trading.trading_cycle` + `execution.order_executor` + `execution.reconciler` |
| feedback | `feedback_agent.py` | `feedback.outcome_analytics_v2` + `performance_report_generator` + `candidate_profile_registry` |

Orchestrator: `crypto_ai_system.pipeline.orchestrator.Pipeline`. Stage contracts:
`crypto_ai_system.pipeline.contracts` (`StageResult`, `StageStatus`).

Two config systems, both load-bearing:
- `config/settings.py` (root) — flat constants: all storage paths + all flags.
- `src/crypto_ai_system/config.py` — `AppConfig` / `load_config` for src modules.

Root packages `core/`, `config/`, `collectors/`, `builders/`, `risk/`, `bridge/`,
`data_health/` are kept and imported by name (not under `src/`). Do not "fix" this
into `src/` casually — many import sites depend on it.

## Non-negotiable safety rules

The system must **fail closed**. Enforce these in code, never bypass:

1. **No order path is enabled by default.** All live/testnet flags in
   `config/settings.py` default False; `scripts/check_safety_defaults.py` guards this
   and runs in CI. Never flip a default to enable orders.
2. **Live/testnet order submission requires explicit flags + a confirmation phrase.**
   The trading agent (`trading_agent.py`) refuses live/testnet unless enabled and
   confirmed. Keep that guard.
3. **PreOrderRiskGate is mandatory** before any order intent
   (`execution/order_executor.py: build_order_intent`). Do not create intents that
   bypass it.
4. **Secrets are read only by the executor at submission time**, never by the
   research/agent layer, never logged, never written to storage. Redact API
   keys/secrets/signatures in all output.
5. **Testnet endpoints only** for the signed-testnet path — reject any mainnet URL.
6. Actual API-key setup and the first real order submission are the **operator's
   manual action**. Claude implements the code; it does not run live/testnet
   submissions or handle real secret values.

## Conventions

- Match surrounding code style. Type hints on new functions. `from __future__ import annotations`.
- Comments state constraints the code can't show — not narration.
- Keep ASCII in console output paths (Windows cp949 can't encode em-dashes); the
  pipeline reconfigures stdout to UTF-8 in `run_pipeline.py`.
- New tests go in `tests/`. Mark network/real-pipeline tests with
  `@pytest.mark.integration`. Prefer network-free unit tests with injected transports.
- Commit only when asked. Branch off `main` (the lean pipeline is merged to
  `main`). End commit messages with the Claude co-author trailer.

## Current focus

The signed-testnet order adapter (HMAC signing + POST behind the existing
contracts and hard caps) is **implemented and verified** — one order was FILLED
and RECONCILED on testnet (2026-07-15). Remaining work is operator-driven, not new
code: repeated clean testnet sessions, a live read-only probe, then the live
canary one-order boundary (a separate approval + runtime). See `STATUS.md`
"Next steps" for the current gate.
