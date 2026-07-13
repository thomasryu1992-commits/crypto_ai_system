# Merge Validation Summary - Step1~157E Extended

- Legacy base: `crypto_ai_system.zip`
- Extended source: `crypto_ai_system_step157e_full.zip`
- Legacy logical file count, excluding `.git`, `__pycache__`, `*.pyc`, and real secrets: **347**
- Merged logical file count with same exclusions: **460**
- Missing legacy files after merge: **0**
- Added Extended/merged files: **113**

## Validation Commands Executed

```bash
python run_step150_validation.py
python run_step157e_full_validation.py
```

## Safety Flags

- `LIVE_TRADING_ENABLED=false`
- `TESTNET_SIGNED_ORDER_ENABLED=false`
- `ENABLE_REAL_ORDERS=false`
- `ENABLE_TESTNET_ORDERS=false`

## Notes

The package preserves all legacy Step1~150 files, except intentionally excluded generated/cache/sensitive files. The real Google service account JSON was removed and replaced with `secrets/google_service_account.example.json`. Extended is now the default adapter path via `.env.example`, `config/settings.py`, and `config/settings.yaml`, while legacy Binance fields remain only for backward compatibility.
