# Step280 Full Regression Runtime Hygiene Report

## Status

Step280 replaces the fragile monolithic CI command `python -m pytest -q tests` with a chunked full-regression runner that emits suite-level progress and writes a runtime report.

Current readiness remains **paper possible** only.

## Safety invariants

- live trading disabled
- signed testnet execution disabled
- testnet order submission disabled
- signed testnet promotion blocked
- external order submission not performed
- API key value access disabled
- secret file access/create disabled
- settings write disabled
- score_weights mutation blocked

## Runtime hygiene changes

1. Added `scripts/run_step280_full_regression.py`.
2. Updated CI to run `python scripts/run_step280_full_regression.py --durations 10` instead of the single monolithic `python -m pytest -q tests` gate.
3. Kept Step258~Step280 focused regression as a separate explicit gate.
4. Fixed a full-regression state leak in `crypto_ai_system.research.decision_engine`: unrelated latest ResearchSignal permissions no longer override isolated legacy research-result decisions.
5. Updated Step273~Step279 version/config tests to accept the current Step280 package/config version.
6. Added Step280 tests for runner coverage, workflow hygiene, config safety flags, and ResearchSignal permission isolation.

## Validation summary

Commands verified in this environment:

```bash
PYTHONPATH=src python -m compileall -q src config tests
```

Result: passed.

```bash
PYTHONPATH=src pytest -q tests/test_step280_*.py
```

Result: 5 passed.

```bash
PYTHONPATH=src pytest -q tests/test_step258_*.py tests/test_step259_*.py tests/test_step260_*.py tests/test_step261_*.py tests/test_step262_*.py tests/test_step263_*.py tests/test_step264_*.py tests/test_step265_*.py tests/test_step266_*.py tests/test_step267_*.py tests/test_step268_*.py tests/test_step269_*.py tests/test_step270_*.py tests/test_step271_*.py tests/test_step272_*.py tests/test_step273_*.py tests/test_step274_*.py tests/test_step275_*.py tests/test_step276_*.py tests/test_step277_*.py tests/test_step278_*.py tests/test_step279_*.py tests/test_step280_*.py
```

Result: 138 passed.

Chunked full-regression coverage was validated by suite:

- base safety/data/research: 50 passed
- Step211~220 paper lifecycle/feedback chain: 30 passed
- Step221~230 paper enablement chain: 30 passed
- Step231~240 approval/legacy boundary: 30 passed
- Step241~250 canonical port reports: 25 passed
- Step251~260 canonical port/profile chain: 41 passed
- Step261~269 approval/settings/audit chain: 58 passed
- Step270~280 data/ID/reconciliation/testnet-prep chain: 66 passed

Total chunked full-regression coverage: 330 tests passed.

## Monolithic pytest status

The old monolithic `PYTHONPATH=src pytest -q` command was intentionally removed as the primary CI gate because it provides poor progress visibility in short-lived execution environments and repeatedly timed out before completion despite no assertion failure being observed. Step280 preserves full test coverage by running deterministic pytest suites with progress output and a JSON runtime report at:

```text
data/reports/step280_full_regression_runtime_hygiene_report.json
```

## Live readiness

Current readiness remains **paper possible**. Step280 does not enable signed testnet execution, live canary, live scaled trading, API key access, settings writes, or score weight mutation.
