# Step162 Preserve Repackage Audit

## Purpose
This package was rebuilt from `crypto_ai_system_step162_feature_store_research_signal.zip` with a conservative cleanup policy.

The goal is to keep all currently usable system functions, runners, modules, data fixtures, tests, and documents while removing only non-functional generated cache artifacts.

## Cleanup Policy

### Removed
- `__pycache__/` directories
- `.pytest_cache/`
- `*.pyc` compiled Python cache files
- `.DS_Store` if present

### Preserved
- All source code under `src/crypto_ai_system/`
- All top-level legacy/operational modules such as `core/`, `collectors/`, `research/`, `trading_bot/`, `execution/`, `storage_layer/`, `knowledge_engine/`, etc.
- All runner scripts from Step80 through Step162
- All tests, including legacy safety tests and current Step158-Step162 tests
- All storage snapshots, CSV fixtures, raw data examples, reports, and backup files included in the original package
- All documentation, manifests, and validation reports

## Important Decision
Earlier cleanup removed too much by treating top-level modules as obsolete duplicates. In this preserve repackage, those modules are kept because they may still be used by existing runners and operational flows.

## Duplicate Review
Exact duplicate files mostly fall into these categories:
- Empty `__init__.py` files, which are expected and should not be removed.
- Snapshot aliases such as `latest` files and historical backup files, which are useful for local validation and operational continuity.
- Storage/export CSV samples, which are retained as fixtures and runtime examples.

No functional duplicate source module was removed in this version.

## Test Handling
No test file was removed.

Reason:
- Step130 and Step150 tests still validate trading safety, idempotency, retry, and execution guard behavior.
- Step158 tests validate price data integration.
- Step159/160 tests validate data foundation and ResearchSignal.
- Step161 tests validate extra data collection.
- Step162 tests validate Feature Store and ResearchSignal v2 permission logic.

## Test Command
Use:

```bash
python -m pytest -q
```

`pytest.ini` was added so the package resolves both `src/` package imports and top-level legacy imports without manually setting `PYTHONPATH`.

## Current Development Status
Step162 remains the active state:

```text
Extra Data Collector
→ Extra Feature Store
→ Research Feature Matrix
→ Research Engine Score Weight
→ ResearchSignal v2 Permission Foundation
```

Next step:

```text
Step163: Connect ResearchSignal v2 trade_permission to the Trading Bot Permission Gate.
```

## Validation Runner Safety Patch
Two validation runners were updated so local validation does not hang on external public APIs by default:

- `run_step161_extra_data_validation.py`
- `run_step162_feature_research_validation.py`

Default behavior:
- Binance Futures, Coin Metrics, and DefiLlama network collectors are disabled only inside these validation runners.
- Farside CSV remains enabled because it is local input.
- Production/data-collection runner `run_additional_data_collector.py` still preserves the original collector behavior.

To validate real external APIs, run:

```bash
RUN_NETWORK_TESTS=true python run_step161_extra_data_validation.py
RUN_NETWORK_TESTS=true python run_step162_feature_research_validation.py
```
