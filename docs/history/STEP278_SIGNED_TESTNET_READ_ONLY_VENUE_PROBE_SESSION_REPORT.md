# Step278 Signed Testnet Read-Only Venue Probe Session Report

## Status

Readiness remains: **paper possible**.

Step278 is review-only. It does not enable signed testnet execution, does not submit testnet orders, does not call `place_order` or `cancel_order`, and does not access API key values.

## Scope

Step278 adds a signed testnet read-only venue probe session on top of the Step277 dry-run session recorder.

The new chain is:

```text
Step277 dry-run session recorder
-> dry_run_session_sha256
-> operator read-only probe acknowledgement
-> read-only venue probe evidence
-> balance/position/open orders/orderbook/fee/slippage/min-order/fetch-order probes
-> place/cancel order disabled contract evidence
-> probe event log
-> probe close report
-> read_only_venue_probe_session_sha256
```

## Safety invariants

The following remain hard disabled:

```text
ready_for_signed_testnet_execution = false
testnet_order_submission_allowed = false
external_order_submission_performed = false
place_order_enabled = false
cancel_order_enabled = false
signed_order_executor_enabled = false
adapter_place_order_called = false
adapter_cancel_order_called = false
```

## Added files

- `src/crypto_ai_system/execution/signed_testnet_read_only_venue_probe_session.py`
- `tests/test_step278_signed_testnet_read_only_venue_probe_session.py`
- `STEP278_SIGNED_TESTNET_READ_ONLY_VENUE_PROBE_SESSION_REPORT.md`

## Updated files

- `pyproject.toml`
- `config/settings.yaml`
- `README.md`
- `.github/workflows/review_only_chain_validation.yml`
- Step273~Step277 version/config safety assertion tests now point to Step278 project version.

## Validation commands

```bash
PYTHONPATH=src python -m compileall -q src config tests
```

Result: passed

```bash
PYTHONPATH=src pytest -q tests/test_step278_*.py
```

Result: 7 passed

```bash
PYTHONPATH=src pytest -q tests/test_step273_*.py tests/test_step274_*.py tests/test_step275_*.py tests/test_step276_*.py tests/test_step277_*.py tests/test_step278_*.py
```

Result: 40 passed

```bash
PYTHONPATH=src pytest -q tests/test_step211_v5_paper_execution_dry_run_bridge.py tests/test_step212_v5_simulated_paper_order_lifecycle.py tests/test_step213_v5_paper_lifecycle_outcome_store.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py tests/test_step274_*.py tests/test_step275_*.py tests/test_step276_*.py tests/test_step277_*.py tests/test_step278_*.py
```

Result: 57 passed

```bash
PYTHONPATH=src pytest -q tests/test_step258_*.py tests/test_step259_*.py tests/test_step260_*.py tests/test_step261_*.py tests/test_step262_*.py tests/test_step263_*.py tests/test_step264_*.py tests/test_step265_*.py tests/test_step266_*.py tests/test_step267_*.py tests/test_step268_*.py tests/test_step269_*.py tests/test_step270_*.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py tests/test_step274_*.py tests/test_step275_*.py tests/test_step276_*.py tests/test_step277_*.py tests/test_step278_*.py
```

Result: 125 passed

```bash
PYTHONPATH=src pytest -q
```

Result: not completed in this container.

Reason:

```text
timeout: 300 seconds
progress before timeout: about 22%
assertion failures before timeout: none observed
```

## Live readiness judgment

Still **paper possible** only.

Not ready for:

```text
signed testnet execution
live canary
live scaled
```

## Recommended Step279

Step279 should be: **Read-Only Venue Probe Result Validator + Testnet Promotion Blocker**.

Goal:

```text
Step278 read-only probe session required
probe evidence freshness required
all read probes valid required
place/cancel disabled evidence required
probe close report hash valid required
operator acknowledgement valid required
signed testnet execution remains disabled unless a later explicit signed execution step is introduced
```
