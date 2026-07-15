# Crypto AI System Step159~160 Data + Research Completion Report

## Purpose

This package completes the first production foundation for the Crypto AI System:

1. Data Collection Foundation
2. Data Contract / Source Policy
3. Coinalyze derivatives enrichment seam
4. BTC multi-timeframe Price Data integration
5. ResearchSignal-based Research Bot output

Live execution remains intentionally disabled. This version is designed for research, storage, reporting, paper preparation, and execution-readiness validation.

## Data Source Roles

| Source | Role | Trading Allowed |
|---|---|---:|
| extended | live-execution eligible market source | true |
| coinalyze | derivatives enrichment source | false as standalone |
| price_data_binance_tradingview | historical / fallback research source | false |
| sample_extended | development fallback source | false |

## Completed Data Layer

- Extended market bundle collection remains the primary live market source.
- Coinalyze client now has explicit methods for futures markets, open interest history, funding-rate history, liquidation history, and long/short ratio history.
- BTC 15m, 1h, 4h, 1d, 3d, 1w, 1m CSV data remains embedded and is used as historical multi-timeframe research context.
- Data contracts validate OHLCV and derivatives frames before storage and analysis.
- Raw store and normalized store append/deduplicate data by timestamp, symbol, market, timeframe, and source.
- Spreadsheet backup remains an output/sync layer, not the canonical raw store.

## Completed Research Layer

- ResearchBot now emits a canonical ResearchSignal.
- ResearchSignal includes source role, data quality, score, MTF context, market condition, entry side, entry permission, confidence, and block reasons.
- Telegram/report renderers can display block reasons and entry permission clearly.
- TradingBot reads entry fields from the ResearchSignal-style snapshot and respects research-only data blocking.

## Main Commands

```bash
python run_step159_data_foundation.py
python run_step160_research_signal.py
python run_daily_research_report.py
python run_data_health_check.py
PYTHONPATH=src pytest -q
```

## Acceptance Criteria

- BTC 7 timeframe price data loads successfully.
- Extended collection attempts first.
- If Extended fails, price data fallback is used for research only.
- Coinalyze enrichment is attempted when configured and skipped safely when no API key exists.
- `research_signal.json` is created under `storage/latest`.
- `research_signal.jsonl` is appended under `storage/signals`.
- Price data and sample data always block live execution.
- All tests pass.

## Next Recommended Step

Step161 should focus on multi-timeframe backtesting and walk-forward validation before any live order implementation.
