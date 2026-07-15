# Crypto AI System Step1~157E Extended Stable Runbook

This package keeps the original Step1~150 system and adds the Extended Step151E~157E path, but the stable operating path is intentionally narrowed.

## Main commands

```powershell
python fix_storage_permissions.py
python run_stable_pipeline.py
```

To also send the Telegram health message:

```powershell
python run_stable_pipeline.py --send-telegram
```

## Stable execution path

1. `fix_storage_permissions.py`
2. `run_step150_validation.py`
3. `run_step157e_full_validation.py`
4. `run_operational_dry_run.py`
5. `run_spreadsheet_sync.py`
6. `run_system_health_check.py`
7. optional: `send_scheduler_health_report.py`

## Avoid as main entrypoints for now

These legacy runners remain in the repo for compatibility, but should not be used as the primary stable flow until refactored:

- `run_full_cycle.py` directly
- old ad-hoc test scripts
- legacy scheduler `.bat` files without the stable pipeline wrapper

## Health profile

Default:

```env
SCHEDULER_HEALTH_PROFILE=stable
```

This checks the unified stable outputs:

- `step150_validation_result.json`
- `step157e_full_validation_result.json`
- `extended_market_snapshot.json`
- `extended_feature_snapshot.json`
- `research_cycle_result.json`
- `research_decision_result.json`
- `trading_cycle_result.json`
- `operational_dry_run_result.json`
- `spreadsheet_sync_result.json`

Use legacy profile only when debugging old Step1~150 daily scheduler behavior:

```env
SCHEDULER_HEALTH_PROFILE=legacy
```

## Safety

Keep these disabled until Step159E testnet execution is implemented and validated:

```env
LIVE_TRADING_ENABLED=false
ENABLE_REAL_ORDERS=false
TESTNET_SIGNED_ORDER_ENABLED=false
EXCHANGE_ORDER_ENABLED=false
```
