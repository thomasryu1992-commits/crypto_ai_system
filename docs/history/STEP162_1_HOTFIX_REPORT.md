# Step162.1 Hotfix Report

## Purpose
Fix the Step162 extra-data Feature Store integration bug found after live API validation.

## Issues Found
- Binance Futures and DefiLlama data were collected successfully, but the final `research_feature_matrix.csv` kept main extra-data score columns at `0.0`.
- `_x` / `_y` duplicate columns appeared after pandas merge operations.
- `optional_extra_data_available` could be `False` even when Binance or DefiLlama feature frames were available.
- Binance derivatives feature rows were sparse because different Binance endpoints use different timestamps.
- Coin Metrics Exchange Flow could return no usable FlowNet metrics while still being an optional data source.
- Farside ETF Flow is intentionally skipped for now because v1 requires manual CSV input.

## Fixes Applied
- Updated `src/crypto_ai_system/features/research_feature_matrix.py`:
  - Prevents `_x` / `_y` suffix leakage.
  - Drops neutral placeholder score columns before merging real feature groups.
  - Coalesces old suffix columns if they already exist.
  - Adds per-feature-group availability markers.
  - Sets `optional_extra_data_available=True` when any extra feature group is actually merged.
  - Updates matrix version to `step162_1_research_feature_matrix_hotfix`.

- Updated `src/crypto_ai_system/features/additional_data_features.py`:
  - Forward-fills sparse Binance endpoint fields after outer merge.
  - Preserves latest taker ratio, top trader ratio, basis, mark/index, and orderbook values in the latest Binance derivatives snapshot.
  - Keeps USDT/USDC 7d change as `NaN` when symbol-level history is unavailable instead of incorrectly forcing `0.0`.

- Updated `src/crypto_ai_system/data/coinmetrics_exchange_flow_collector.py`:
  - Treats unavailable Community API FlowNet metrics as `neutral_fallback=True` instead of a hard source failure.
  - Adds `data_available`, `candidate_metrics`, and `reason` fields to source status.

- Updated defaults:
  - `FARSIDE_ETF_FLOW_ENABLED=false` in `.env.example`.
  - `additional_data.farside.enabled=false` in `config/settings.yaml`.

## Validation
Executed:

```bash
python -m pytest -q
python run_step162_feature_research_validation.py
python run_step161_extra_data_validation.py
python run_additional_data_collector.py
```

Result:

```text
35 passed
STEP162_FEATURE_RESEARCH_VALIDATION_OK
STEP161_EXTRA_DATA_VALIDATION_OK
ADDITIONAL_DATA_COLLECTOR_OK
```

## Expected Result After Live API Run
When Binance Futures and DefiLlama are enabled and Farside is disabled:

```text
binance_derivatives_score != 0 when Binance feature signal is non-neutral/non-zero
stablecoin_liquidity_score != 0 when stablecoin liquidity changes are detected
exchange_flow_score = 0 when Coin Metrics FlowNet metrics are unavailable
etf_flow_score = 0 when Farside is disabled
optional_extra_data_available = True when Binance or DefiLlama features are merged
_x / _y duplicate columns should not remain in research_feature_matrix.csv
```
