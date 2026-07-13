# Crypto AI System Agent Package Boundary

Version: 0.286.0-agent.14

This package is the Crypto AI System side of the Thomas Agent OS integration. It is not the
Thomas Agent OS Local Launcher and does not implement Launcher-owned import-manager behavior.

## Crypto package responsibilities

- Provide `agent_manifest.json` so the Launcher can identify the package.
- Provide `config/defaults.json` and `config/command_map.json` with safe local defaults.
- Provide `scripts/run_command.py` as the standard command entrypoint.
- Provide `scripts/self_test.py` and `scripts/validate_package.py` for import-time validation.
- Return final-line JSON from dry-run commands so the Launcher or Telegram bridge can parse it.
- Optionally provide Docker attach files for containerized execution.
- Keep live trading, real order execution, withdrawal, fund transfer, and stage transition disabled by default.

## Launcher-owned responsibilities

These are intentionally not implemented in this ZIP:

- `0_IMPORT_ZIP.bat` orchestration.
- `agents_zip_inbox` scanning.
- `agents_installed/*/current` promotion or rollback policy.
- Global `agent_registry.json` mutation.
- Telegram bot routing and `/status` rendering.
- Duplicate package import policy.

The package only exposes the contract that allows the Launcher to do those things.

## Required command contract

```bash
python scripts/run_command.py --command daily --dry-run
python scripts/run_command.py --command scan --symbol BTC --dry-run
python scripts/self_test.py
python scripts/validate_package.py
```

All commands must leave the last stdout line as JSON.

## Safety boundary

The following remain false by default:

```text
live_trading_enabled=false
order_execution_enabled=false
auto_position_open_enabled=false
withdrawal_enabled=false
fund_transfer_enabled=false
execution_permission_granted=false
stage_transition_allowed=false
```
