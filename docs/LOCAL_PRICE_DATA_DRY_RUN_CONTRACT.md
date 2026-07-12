# Local Price Data Dry-Run Contract

Contract version: `price_csv_ohlcv_v1`

This Agent Package may inspect local OHLCV CSV files for review-only source-health reporting. This is not a trading permission layer.

## Default location

`config/defaults.json` uses:

```json
{
  "local_price_data_dir": "data/price_data",
  "local_price_data_max_age_hours": 48
}
```

## Required CSV columns

```text
timestamp,symbol,open,high,low,close,volume
```

Optional marker columns such as `sample_flag`, `fixture_flag`, `mock_flag`, `synthetic_flag`, or `fallback_flag` are treated as review-only blocking markers.

## Eligibility rules

- Missing CSV: `price_data_connected=false`.
- Invalid schema: `price_data_connected=false`.
- Sample / fixture / mock / synthetic / fallback CSV: schema may be valid, but `price_data_connected=false` and all testnet/live candidate flags remain false.
- Stale CSV: `price_data_connected=false`.
- Fresh real local CSV: `price_data_connected=true` is allowed for review-only source-health reporting, but `trading_candidate_allowed=false`, `signed_testnet_candidate_eligible=false`, and `live_candidate_eligible=false` remain unchanged.

## Safety invariants

Local CSV validation must not call exchange endpoints, read secret values, create signed requests, mutate runtime settings, or grant execution permission.
