# Step80 Env Review

This package keeps the original system capabilities while cleaning `.env.example`.

## What changed

- Removed duplicate env keys from `.env.example`.
- Kept canonical keys only in the template.
- Preserved backward-compatible aliases inside `config/settings.py`.
- Restored Spreadsheet / Google Sheets-related configuration.
- Kept Google Sheets disabled by default.
- Kept local CSV spreadsheet export always available.
- Kept live trading hard-blocked.

## Canonical env keys

| Area | Canonical key |
|---|---|
| Coinalyze | `COINALYZE_ENABLED`, `COINALYZE_API_KEY` |
| Telegram | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Spreadsheet | `SPREADSHEET_ENABLED`, `SPREADSHEET_PROVIDER`, `SPREADSHEET_ID`, `SPREADSHEET_WORKSHEET` |
| Google credentials | `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_SERVICE_ACCOUNT_JSON` |
| Runtime | `TRADING_MODE`, `PAPER_TRADING_ENABLED`, `LIVE_TRADING_ENABLED` |

## Supported legacy aliases in code

The new `.env.example` does not show duplicate aliases, but `config/settings.py` still reads common older names such as:

```text
ENABLE_COINALYZE
USE_COINALYZE
ENABLE_TELEGRAM
ENABLE_TELEGRAM_ALERTS
GOOGLE_SHEETS_ENABLED
ENABLE_GOOGLE_SHEETS
GOOGLE_SHEET_ID
GOOGLE_SPREADSHEET_ID
GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CREDENTIALS_JSON
```

This lets existing local `.env` files continue working while keeping the public template clean.
