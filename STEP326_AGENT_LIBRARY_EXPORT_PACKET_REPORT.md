# Step326 Agent Library Export Packet Report

## Status
Implemented Agent Library evidence inclusion in the review-only export packet.

## Added / Updated
- `src/crypto_ai_system/agents/agent_library_export.py`
- `src/crypto_ai_system/reports/review_only_export_packet.py`
- `run_full_cycle.py`
- `run_operational_dry_run.py`
- `tests/agents/test_step326_agent_library_export_packet.py`

## Export Packet Evidence
The review-only packet now includes:
- `agent_contract_index.json`
- `agent_lint_report.json`
- `agent_eval_report.json`
- `agent_contract_review_report.json`
- `agent_permission_policy_report.json`
- `agent_prohibited_action_scan.json`

## Safety
- Agent evidence is review-only.
- Missing Agent Library artifacts are exported as blocked placeholder artifacts.
- Export packet generation does not mutate `settings.yaml` or runtime config.
- Export packet generation does not create approval authority.
- Export packet generation does not enable order submission, signed testnet execution, live canary execution, or live scaled execution.
