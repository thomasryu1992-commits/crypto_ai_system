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

## Current stage: paper (pre-live)

| Concern | State |
|---|---|
| Pipeline end-to-end | ✅ runs (all five stages OK on real data) |
| Data source | ✅ real Binance USD-M Futures public klines (read-only, no key); synthetic fallback on failure |
| Order submission | ❌ paper only; no signed/live order path implemented |
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
2. Implement the signed-testnet order adapter (HMAC signing + POST) behind the existing contracts (idempotency, client order id, timeout, bounded retry, endpoint allowlist).
3. Verify a testnet session end-to-end (fill / position / balance reconciliation).
4. Live canary.

## History

Pre-refactor state (the over-engineered governance/evidence apparatus) is frozen
at tag/branch `archive/pre-lean-2026-07-15`. Development reports are in `docs/history/`.
