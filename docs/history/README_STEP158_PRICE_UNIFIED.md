# Crypto AI System Step158 Price Unified

This package keeps the Step1~157E Extended stable system and adds the missing embedded BTC price-data layer.

## What changed

1. Embedded BTC price history was restored and included under:
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_15m.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_1h.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_4h.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_1d.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_3d.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_1w.csv`
   - `data/price_data/BINANCE_BTCUSDT_P/btcusdtp_1m.csv`

2. Added `crypto_ai_system.data.price_data_loader`.
   - Normalizes TradingView/Binance CSVs into internal OHLCV format.
   - Builds a BTC multi-timeframe price context.
   - Uses 1h as the primary fallback timeframe by default.

3. ResearchBot now includes multi-timeframe price context in the snapshot/report.
   - `price_context`
   - `mtf_alignment_score`
   - `mtf_bias`
   - per-timeframe close/trend/RSI/change fields

4. Extended API failure now falls back in this order:
   - Extended live API
   - embedded BTC price CSV data
   - synthetic sample data only if price data is unavailable

5. Trading safety was strengthened.
   - Only `source == extended` is allowed to flow into order intent.
   - Embedded CSV price data is valid for research/backtest context but blocked for live execution.
   - Sample/fallback/synthetic data remains blocked.

6. Fixed known Step157E issues.
   - `spreadsheet_backup` path alias restored.
   - raw store changed to append-and-deduplicate behavior.
   - `TradingBot` position-size tuple bug fixed.
   - `target_price` now receives stop price, not risk-per-unit.
   - legacy pytest import errors fixed with safe compatibility wrappers.

## Main commands

```bash
python run_daily_research_report.py
python run_collect_raw_data.py
python run_step157e_full_validation.py
PYTHONPATH=src pytest -q
```

Expected validation status in this package:

```text
pytest: 20 passed
run_daily_research_report.py: OK
run_collect_raw_data.py: OK
run_step157e_full_validation.py: OK
```

`run_stable_pipeline.py` components were also run individually. In this environment, the combined stable runner timed out while waiting on the Step157E subprocess, but the same Step157E validation completed successfully when executed directly.

## Safety note

The included Binance/TradingView price CSVs are historical/research data. They are not treated as a live execution feed. When the pipeline uses these files as the source, the snapshot marks:

```text
trading_allowed_by_data_source = false
NON_LIVE_EXECUTION_DATA_SOURCE:price_data_binance_tradingview
```

That means Telegram/research/backtest can use them, but Extended live order intent is blocked until real Extended live data is collected.
