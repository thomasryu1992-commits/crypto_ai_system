# CHANGELOG — Step151E to Step157E

## Step151E — Extended Market Adapter Layer

- Added `ExtendedClient`.
- Added `symbol_mapper.py`.
- Introduced canonical symbol separation:
  - internal: `BTC-PERP`
  - Extended market: `BTC-USD`
  - quote: `USD`
  - settlement: `USDC`
- Removed Binance collector from the main data flow.

## Step152E — Extended Real Data Collector

- Added Extended candles collection:
  - trades candles
  - mark price candles
  - index price candles
- Added Extended funding history collection.
- Added Extended open interest history collection.
- Added recent trades/liquidation event seam.
- Added orderbook snapshot/spread guard seam.

## Step153E — Extended Feature Store

- Added mark/index basis features.
- Added mark/last basis features.
- Added spread bps feature.
- Added funding z-score.
- Added OI 4H change.
- Preserved ATR, RSI, ADX, MA/EMA, liquidation spike, market regime.

## Step154E — Extended-specific Backtest

- Backtest is now configured for Extended:
  - settlement asset: USDC
  - maker fee: 0 bps
  - taker fee: 2.5 bps
  - default slippage: 3 bps
- Added funding payment approximation.

## Step155E — Extended Entry Policy v2

- Added spread filter.
- Added funding filter modes:
  - off
  - normal
  - strict
- Added OI filter modes:
  - off
  - normal
  - strict
- Preserved trend/range/liquidation reversal scaffolds.

## Step156E — Extended Exit Policy v2

- Preserved ATR stop + min/max bps guard.
- Preserved TP1 partial close.
- Preserved breakeven after TP1.
- Preserved trailing stop after TP1 in trend regimes.
- Preserved time-based stop.

## Step157E — Extended Parameter Sweep

- Added Extended-specific parameter sweep.
- Sweep includes:
  - ATR multiplier
  - TP1 R
  - TP1 size
  - trailing ATR multiplier
  - time stop candles
  - funding filter mode
  - OI filter mode
  - spread guard bps
- Generates Extended strategy comparison report.

## Preserved from Step150/156

- Spreadsheet-first architecture.
- Local CSV backups.
- Retry queue.
- Append-only event log.
- Coinalyze enrichment seam.
- Safety guards that block live/testnet signed execution.
