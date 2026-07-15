# Step162.2 Timestamp-Safe Feature Matrix Hotfix

## Purpose

Step162.1 fixed optional-data score reflection, suffix-column leakage, and neutral fallback behavior. The remaining issue was timestamp leakage: fresh optional API snapshots could be broadcast across historical price rows, which is acceptable for a single live signal but unsafe for backtests and regression tests.

Step162.2 separates live matrix behavior from backtest-safe matrix behavior.

## Key Fixes

- Added timestamp-safe Feature Matrix modes:
  - `live`: latest optional API snapshot can be applied only to the latest row.
  - `backtest`: optional data is attached only when `feature_timestamp <= price_timestamp`.
- Strips broadcast optional-data snapshot columns before Feature Matrix merging.
- Adds explicit feature timestamp columns:
  - `extra_derivatives_features_timestamp`
  - `stablecoin_liquidity_features_timestamp`
  - `exchange_flow_features_timestamp`
  - `etf_flow_features_timestamp`
- Adds separate output files:
  - `storage/features/research_feature_matrix_live.csv`
  - `storage/features/research_feature_matrix_backtest.csv`
  - `storage/features/research_feature_matrix.csv` as live alias for backward compatibility.
- Research matrix files now overwrite old matrix files instead of appending, preventing old unversioned rows from mixing with new live/backtest rows.
- Keeps optional API fail-soft behavior:
  - Coin Metrics unavailable data remains neutral fallback.
  - Farside disabled remains neutral fallback.

## Modified Files

- `src/crypto_ai_system/features/research_feature_matrix.py`
- `src/crypto_ai_system/research/research_bot.py`
- `src/crypto_ai_system/research/raw_score_pipeline.py`
- `src/crypto_ai_system/config.py`
- `config/settings.yaml`
- `.env.example`
- `tests/test_step162_feature_store_signal.py`

## Validation

```text
python -m pytest -q
38 passed
```

Runner checks:

```text
python run_step162_feature_research_validation.py
STEP162_FEATURE_RESEARCH_VALIDATION_OK

python run_step161_extra_data_validation.py
STEP161_EXTRA_DATA_VALIDATION_OK

python run_additional_data_collector.py
ADDITIONAL_DATA_COLLECTOR_OK

python run_trading_cycle.py
Trading cycle: NONE paper=NO_SIGNAL
```

## Next Step

After Step162.2, the system can safely move to Step163:

ResearchSignal v2 `trade_permission` → Trading Bot Permission Gate.
