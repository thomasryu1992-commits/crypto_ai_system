# Daily / Scan Report Contract v2

This package emits Markdown artifacts for `daily` and `scan` commands under `data/reports/` while preserving the Thomas Agent OS final-line JSON contract.

## Contract

- `artifact_contract_version: agent_report_v2`
- YAML front matter is required.
- Review-only and safety fields must be explicit.
- Missing optional data is marked as neutral reporting context only.
- Reports must not create order intents, signed requests, endpoint calls, or runtime mutations.

## Required safety fields

- `live_trading_enabled: false`
- `order_execution_enabled: false`
- `auto_position_open_enabled: false`
- `withdrawal_enabled: false`
- `fund_transfer_enabled: false`
- `execution_permission_granted: false`
- `stage_transition_allowed: false`
- `order_endpoint_called: false`
- `secret_value_accessed: false`

## Launcher boundary

The Crypto AI System ZIP owns command output artifacts. Thomas Agent OS owns import, registry, Telegram routing, and installation lifecycle.
