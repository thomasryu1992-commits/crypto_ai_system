# Step161 - Additional BTC Data Collection Integration

## Purpose

This update adds the extra BTC data collection layer requested in the `BTC Trading System - additional data collection` specification.

The system now supports four additional data groups:

1. Binance Futures Public API
   - Open Interest now/history
   - Funding Rate
   - Mark / Index Price
   - Taker Buy/Sell Volume
   - Global Long/Short Ratio
   - Top Trader Account / Position Ratio
   - Basis
   - Orderbook Depth
   - Binance Futures Klines

2. Coin Metrics Community API
   - BTC exchange netflow
   - Exchange-level netflow for Binance, Coinbase, OKX, Bybit, Kraken
   - Native BTC and USD-denominated flow metrics where available

3. Farside Investors BTC ETF Flow
   - Manual CSV ingestion for BTC ETF daily flow
   - IBIT / FBTC / GBTC / Total Flow normalization
   - 5-day and 20-day flow features

4. DefiLlama Stablecoin API
   - Total stablecoin market cap
   - USDT / USDC market cap where available
   - 7-day and 30-day liquidity change features

## New Code Files

```text
src/crypto_ai_system/data/binance_futures_collector.py
src/crypto_ai_system/data/coinmetrics_exchange_flow_collector.py
src/crypto_ai_system/data/defillama_stablecoin_collector.py
src/crypto_ai_system/data/farside_etf_flow_collector.py
src/crypto_ai_system/data/additional_data_collector.py
src/crypto_ai_system/features/additional_data_features.py
run_additional_data_collector.py
run_step161_extra_data_validation.py
tests/test_step161_extra_data.py
data/raw/etf/farside_btc_etf_flow.csv.example
```

## Feature Store Outputs

The additional layer creates these feature tables when source data is available:

```text
storage/features/binance_derivatives_features.csv
storage/features/exchange_flow_features.csv
storage/features/etf_flow_features.csv
storage/features/stablecoin_liquidity_features.csv
storage/latest/additional_data_snapshot.json
storage/latest/additional_feature_snapshot.json
```

## ResearchSignal v2 Additions

ResearchSignal now includes:

```json
"score_components": {
  "structure": 0.0,
  "momentum": 0.0,
  "derivatives": 0.0,
  "exchange_flow": 0.0,
  "etf_flow": 0.0,
  "stablecoin_liquidity": 0.0,
  "risk": 0.0,
  "onchain": 0.0
}
```

And feature-level context:

```json
"features": {
  "binance_derivatives_score": 0.0,
  "exchange_flow_score": 0.0,
  "etf_flow_score": 0.0,
  "stablecoin_liquidity_score": 0.0,
  "exchange_netflow_1d": 0.0,
  "exchange_netflow_zscore_30d": 0.0,
  "etf_flow_1d": 0.0,
  "etf_flow_5d": 0.0,
  "stablecoin_supply_change_7d": 0.0,
  "taker_buy_sell_ratio": 0.0,
  "top_trader_long_short_ratio": 0.0
}
```

## Trading Permission Logic Added

The entry gate now blocks or reduces conviction when any of these appear:

- Extreme exchange-flow sell pressure
- Binance derivatives crowding
- ETF outflow pressure
- Stablecoin liquidity contraction
- Existing spread / funding / OI / data-source blocks

## Config

New settings are under:

```yaml
additional_data:
  enabled: true
  binance_futures:
    enabled: true
  coinmetrics:
    enabled: true
  farside:
    enabled: true
  defillama:
    enabled: true
```

Environment variables were added to `.env.example`.

## How to Run

Collect only the additional data layer:

```bash
python run_additional_data_collector.py
```

Run raw-data-to-research validation with the additional layer:

```bash
python run_step161_extra_data_validation.py
```

Run the existing research signal pipeline:

```bash
python run_step160_research_signal.py
```

Run tests:

```bash
PYTHONPATH=src pytest -q
```

## Validation Result

The integrated package was validated with:

```text
29 passed
```

## Notes

- Farside ETF flow is intentionally implemented as manual CSV ingestion first because its public table is not a stable official API.
- Public API collectors are fail-soft. If a source is unavailable, the main data/research/trading cycle continues and records source status instead of crashing.
- Price CSV data remains in the system as the multi-timeframe context layer: BTC 15m, 1h, 4h, 1d, 3d, 1w, 1m.
