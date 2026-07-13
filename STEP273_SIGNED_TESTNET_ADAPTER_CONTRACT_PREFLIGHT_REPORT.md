# Step273 Signed Testnet Adapter Contract Preflight Report

## Scope

Step273 defines a review-only signed testnet adapter contract and pre-testnet readiness gate. It does not enable signed testnet execution, live execution, external order submission, API key access, secret file creation, settings mutation, or runtime score weight mutation.

## Added Components

- `src/crypto_ai_system/execution/exchange_adapter_contract.py`
- `src/crypto_ai_system/execution/signed_testnet_readiness.py`
- `tests/test_step273_signed_testnet_adapter_contract.py`

## Safety Invariants

```text
live trading disabled
signed testnet order disabled
place_order disabled
cancel_order disabled
external_order_submission_performed=false
API key values blocked if passed into readiness validation
secret file access blocked
live key scope blocked
non-testnet base URL blocked
manual signed approval required
```

## Readiness Semantics

`contract_review_ready=true` means the adapter contract metadata, secret metadata, approval metadata, venue preflight metadata, and risk limits are internally consistent for review.

It does not mean testnet orders can be placed. Step273 always returns:

```text
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_performed=false
```

## Validation Results

```bash
PYTHONPATH=src python -m compileall -q src config tests
```

Result: passed.

```bash
PYTHONPATH=src pytest -q tests/test_step273_*.py
```

Result: 7 passed.

```bash
PYTHONPATH=src pytest -q tests/test_step211_v5_paper_execution_dry_run_bridge.py tests/test_step212_v5_simulated_paper_order_lifecycle.py tests/test_step213_v5_paper_lifecycle_outcome_store.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py
```

Result: 24 passed.

```bash
PYTHONPATH=src pytest -q tests/test_step258_*.py tests/test_step259_*.py tests/test_step260_*.py tests/test_step261_*.py tests/test_step262_*.py tests/test_step263_*.py tests/test_step264_*.py tests/test_step265_*.py tests/test_step266_*.py tests/test_step267_*.py tests/test_step268_*.py tests/test_step269_*.py tests/test_step270_*.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py
```

Result: 92 passed.

```bash
PYTHONPATH=src pytest -q
```

Result: not completed because the container timed out after 300 seconds. The run progressed past 25% with no assertion failure visible before timeout.

## Live Readiness

Current readiness remains `paper possible`. The package is not signed-testnet-ready and not live-canary-ready.
