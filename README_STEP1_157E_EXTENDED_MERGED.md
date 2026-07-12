# Crypto AI System Step1~157E Extended Merged Full

This package uses the original `crypto_ai_system.zip` as the base and merges the Extended Step151E~157E roadmap into it.

## What is preserved

- Legacy research bot, knowledge base, knowledge engine, research decision flow
- Raw data storage and market context builders
- Trading bot, paper watch, regression/forward-test scaffolding
- Execution guard, risk guard, order state, reconciliation, mock/testnet skeletons
- Spreadsheet-first integrations, retry queue, local CSV backup, Telegram dry-run flow
- Step80/120/130/150 validation assets and review artifacts

## What is added

- `src/crypto_ai_system/` Extended adapter package
- Extended market identity: `BTC-PERP` canonical symbol, `BTC-USD` exchange market, `USD` quote, `USDC` settlement
- Extended raw collector, feature store, market regime, score engine, backtest, exit policy, parameter sweep
- Step151E, Step152E, Step154E, Step157E runners
- Extended validation runner

## Safety

- `LIVE_TRADING_ENABLED=false`
- `TESTNET_SIGNED_ORDER_ENABLED=false`
- No real service account JSON is included. Use `secrets/google_service_account.example.json` as a template.

## Main validation commands

```bash
python run_step150_validation.py
python run_step157e_full_validation.py
```

## Extended commands

```bash
python run_step151e_extended_market_check.py
python run_step152e_build_extended_features.py
python run_step154e_extended_backtest.py
python run_step157e_parameter_sweep.py
```

## Notes

Binance-specific modules are retained for backward compatibility and historical tests, but Extended is now the default path through `.env.example`, `config/settings.py`, and `config/settings.yaml`. Coinalyze remains available as an optional auxiliary derivatives data source.

## Windows storage/logs PermissionError quick fix

If `run_operational_dry_run.py` fails with `PermissionError: storage/logs/event_log.jsonl`, run:

```powershell
python fix_storage_permissions.py
python run_operational_dry_run.py
python send_scheduler_health_report.py
```

This usually happens when the extracted ZIP leaves `event_log.jsonl` read-only, locked, or accidentally created as a directory. Event logging is non-critical telemetry, so `core/event_log.py` now falls back to `storage/logs/event_log_fallback.jsonl` instead of crashing the pipeline.
