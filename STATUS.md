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
4. ✅ Testnet reconciliation implemented (order/position/balance vs intent). **Operator step**: run it against a real testnet order to verify a session end-to-end.
5. Live canary.

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

## History

Pre-refactor state (the over-engineered governance/evidence apparatus) is frozen
at tag/branch `archive/pre-lean-2026-07-15`. Development reports are in `docs/history/`.
