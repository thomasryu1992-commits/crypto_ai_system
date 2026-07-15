# Step293 — PreOrderRiskGate Full Policy Expansion Report

## Goal

Expand the PreOrderRiskGate from a basic review/paper blocker into a full policy gate that can support the later signed-testnet and live-canary readiness chain while keeping all order submission disabled.

## Scope

Modified:

- `src/crypto_ai_system/trading/pre_order_risk_gate.py`
- `tests/test_step293_pre_order_risk_gate_full_policy_expansion.py`
- `README.md`
- `CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md`
- `scripts/status_consistency_checker.py`
- `.github/workflows/review_only_chain_validation.yml`
- `scripts/run_step280_full_regression.py`
- `tests/test_step282_canonical_status_sync.py`

## Implemented behavior

The PreOrderRiskGate now returns explicit `status` values in addition to legacy-compatible `block_reasons`.

Allowed status values:

- `PASS_REVIEW_ONLY`
- `PASS_PAPER`
- `PASS_SIGNED_TESTNET`

Blocking status values include:

- `BLOCK_INVALID_CANONICAL_ID_CHAIN`
- `BLOCK_PROFILE_UNAPPROVED`
- `BLOCK_PROFILE_HASH_MISMATCH`
- `BLOCK_PROFILE_HASH_MISSING`
- `BLOCK_STALE_DATA`
- `BLOCK_FALLBACK_OR_SYNTHETIC`
- `BLOCK_SAMPLE_DATA`
- `BLOCK_OPTIONAL_DATA_HEALTH`
- `BLOCK_POSITION_LIMIT`
- `BLOCK_DAILY_LOSS_LIMIT`
- `BLOCK_CONSECUTIVE_LOSS`
- `BLOCK_SPREAD_SLIPPAGE`
- `BLOCK_API_ERROR_RATE`
- `BLOCK_RECONCILIATION_MISMATCH`
- `BLOCK_MANUAL_KILL_SWITCH`
- `BLOCK_MIN_ORDER_SIZE`
- `BLOCK_MAX_ORDER_NOTIONAL`
- `BLOCK_DAILY_ORDER_COUNT`
- `BLOCK_FEE_MODEL`
- `BLOCK_BALANCE_MARGIN`
- `BLOCK_LEVERAGE_LIMIT`
- `BLOCK_VENUE_READINESS`
- `BLOCK_STAGE_EXECUTION_DISABLED`
- `BLOCK_RESEARCH_PERMISSION`

## Full policy checks

The expanded gate checks:

- approved profile
- profile hash match
- canonical ID chain completeness
- data freshness
- optional data health for promotion candidates
- fallback/synthetic/sample blocks
- position limit
- daily loss limit in R and USDT
- max consecutive loss
- daily order count
- spread/slippage
- API error rate
- reconciliation mismatch
- manual kill switch
- min order notional
- max order notional
- fee model evidence
- balance/margin sufficiency
- leverage limit
- venue readiness
- stage-specific execution disable flags
- ResearchSignal trade permission

## Safety invariants

The gate remains metadata-only and does not:

- submit orders
- call exchange endpoints
- read API key values
- create secret files
- mutate `settings.yaml`
- mutate runtime score weights
- apply candidate profiles
- promote to signed testnet or live

## Validation

Executed commands:

```bash
PYTHONPATH=src:. python -m compileall -q src config tests scripts bridge
PYTHONPATH=src:. python scripts/status_consistency_checker.py
PYTHONPATH=src:. pytest -q tests/test_step282_canonical_status_sync.py tests/test_step293_pre_order_risk_gate_full_policy_expansion.py
PYTHONPATH=src:. pytest -q tests/test_step258_*.py ... tests/test_step280_*.py
PYTHONPATH=src:. pytest -q tests/test_step281_*.py ... tests/test_step293_*.py
PYTHONPATH=src:. python run_operational_dry_run.py
PYTHONPATH=src:. python run_full_cycle.py
```

Observed results:

- compileall: PASSED
- status consistency checker: PASSED
- Step282 + Step293 focused tests: 9 passed
- Step258~Step280 focused tests: 138 passed
- Step281~Step293 focused tests: 67 passed
- operational dry run: PASSED
- full cycle: BLOCK_DATA_HEALTH / NO_ORDER

A monolithic Step258~Step293 pytest command exceeded the sandbox timeout, so the same focused regression range was validated in chunks.

## Current stage

The system remains in review-only / shadow / paper-preparation. Signed testnet execution and live trading remain disabled.
