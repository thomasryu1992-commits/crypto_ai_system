# Changelog — Step1~157E Full Extended Rebuild

## Fixed

- Restored the missing Research Bot layer.
- Restored Raw data collection and raw CSV persistence.
- Restored weighted scoring from raw/feature data.
- Restored market condition analysis using score, regime, volatility, liquidity, and derivatives state.
- Restored scenario generation and daily research report output.
- Restored trading-cycle bridge: research snapshot → signal → risk-sized trade plan.
- Restored paper watch scaffold.
- Restored Telegram dry-run summary scaffold.
- Preserved Spreadsheet-first backup structure and retry queue seam.
- Preserved Coinalyze enrichment seam.

## Changed

- Binance main-flow collector removed/replaced by Extended.
- Internal symbol model now separates:
  - canonical_symbol: BTC-PERP
  - exchange_market: BTC-USD
  - quote_asset: USD
  - settlement_asset: USDC

## Excluded

- Temporary one-off test scripts.
- Duplicate old incremental files.
- Actual signed Extended testnet orders.
- Live trading.
