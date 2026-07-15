# STEP164 Permission Audit / Telegram / Paper Risk-Level Report

## Purpose
Step164 adds operational observability after the Step163 permission gate.

The system now records why the Trading Bot allowed, reduced, or blocked a trade and exposes that information in Telegram summaries and paper-trading reports.

## Added Capabilities

### 1. Permission Gate Audit Log
Every trading cycle now writes a permission-gate audit record.

Files:
- `storage/logs/permission_gate_audit.jsonl`
- `storage/latest/permission_gate_audit_latest.json`

Each audit record includes:
- signal
- confidence
- permission gate applied flag
- allow_long / allow_short / allow_new_position
- risk_level
- position_size_multiplier
- paper_status
- research_signal_id
- block_reasons
- risk_warnings
- decision reasons

### 2. Telegram Signal Message Upgrade
Daily Telegram summaries now include:
- Trade Permission section
- Paper Risk-Level Report section
- risk_level
- allow_new_position
- position_size_multiplier
- block_reasons
- risk_warnings
- normal / reduced / blocked attempt counts

### 3. Paper Trading Report by Risk Level
Paper trading now produces a risk-level report based on permission audit rows.

File:
- `storage/latest/paper_risk_level_report.json`

The report groups attempts and results by:
- normal
- reduced
- blocked

Tracked fields include:
- audit_count
- position_opened_count
- blocked_count
- no_signal_count
- closed_trade_count
- win_count
- loss_count
- total_pnl_r
- avg_pnl_r

## Added Files

- `trading/permission_audit.py`
- `trading/paper_report.py`
- `src/crypto_ai_system/trading/permission_audit.py`
- `tests/test_step164_permission_audit_telegram_report.py`
- `run_step164_permission_telegram_validation.py`
- `STEP164_PERMISSION_AUDIT_TELEGRAM_REPORT.md`
- `STEP164_BUILD_VALIDATION.json`

## Modified Files

- `trading/trading_cycle.py`
- `trading/paper_engine.py`
- `notify/telegram_summary_builder.py`
- `src/crypto_ai_system/notifier/telegram.py`
- `src/crypto_ai_system/notifier/summary_builder.py`
- `config/settings.py`
- `config/settings.yaml`
- `.env.example`
- `README.md`

## Validation

Commands:

```bash
python -m pytest -q
python run_step164_permission_telegram_validation.py
python run_trading_cycle.py
python run_step162_feature_research_validation.py
python run_step161_extra_data_validation.py
python run_additional_data_collector.py
```

Results:

```text
47 passed
STEP164_PERMISSION_TELEGRAM_VALIDATION_OK
Trading cycle: NONE paper=BLOCKED_BY_PERMISSION_GATE
STEP162_FEATURE_RESEARCH_VALIDATION_OK
STEP161_EXTRA_DATA_VALIDATION_OK
ADDITIONAL_DATA_COLLECTOR_OK
```

## Next Step
Step165 should focus on Telegram dry-run delivery, scheduler integration, and end-to-end daily operation flow.
