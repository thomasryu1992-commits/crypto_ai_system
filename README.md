# crypto_ai_system - Step 66 Full Package

This package includes the Step 66 fix for Windows `cp949` console encoding errors.

## What was fixed

`run_trading_cycle.py` previously failed on Windows when printing Telegram alert text containing emoji such as `🤖`.

The fix adds UTF-8 stdout/stderr reconfiguration and `safe_print()` handling through:

```python
from core.console import configure_utf8_console, safe_print
configure_utf8_console()
```

The problematic print logic is now:

```python
safe_print(result.get("telegram_alert"))
```

## Quick start

```powershell
cd C:\Users\thomas\Desktop\Coding\crypto_AI_Agent\crypto_ai_system
copy .env.example .env
python run_trading_cycle.py
python run_operational_dry_run.py
python check_scheduler_health.py
```

Expected final health result:

```text
Status: HEALTHY
Operational Dry Run: PASSED
Error Failures: 0
Warning Failures: 0
```

## File structure

```text
crypto_ai_system/
  run_real_market_data_collector.py
  build_market_snapshot.py
  build_market_context.py
  run_dynamic_setup.py
  run_research_cycle.py
  run_research_decision.py
  run_trading_cycle.py
  run_operational_dry_run.py
  check_scheduler_health.py
  reset_storage.py
  config/
  core/
  collectors/
  builders/
  research/
  trading/
  notify/
  integrations/
  storage/
```

## Important outputs

```text
storage/coinalyze_market_data.json
storage/market_snapshot.json
storage/market_context.json
storage/dynamic_setup_result.json
storage/research_cycle_result.json
storage/research_decision_result.json
storage/trading_cycle_result.json
storage/telegram_alert_result.json
storage/spreadsheet_sync_result.json
storage/operational_dry_run_result.json
storage/scheduler_health_result.json
storage/scheduler_logs/daily_operational_dry_run.log
```

## Notes

- The default mode is `paper`.
- This package does not send real exchange orders.
- If Telegram credentials are empty, the Telegram module records a dry-run `SENT` result so the operational pipeline can still pass.
- If Coinalyze is disabled or the API key is missing, the collector generates a stable fallback market data snapshot.
