# Step321 Initial Agent Contracts Report

Status: review-only Agent Library contract foundation added.

Added initial agent contracts:

- `agents/approval/approval_intake_validator.md`
- `agents/approval/signed_testnet_unlock_preview_agent.md`
- `agents/risk/kill_switch_auditor.md`
- `agents/risk/hard_cap_reviewer.md`
- `agents/qa/artifact_integrity_auditor.md`

Added permission policies:

- `agent_contracts/permissions/read_only.yaml`
- `agent_contracts/permissions/paper_only.yaml`
- `agent_contracts/permissions/approval_required.yaml`
- `agent_contracts/permissions/prohibited_actions.yaml`

Safety result:

- `can_modify_runtime=false` required for every contract.
- `can_submit_orders=false` required for every contract.
- Agent contracts are review-only governance artifacts, not runtime executors.
- Agent contracts do not grant signed testnet, live canary, or live scaled execution permission.
- Missing or uncertain evidence requires `blocked=true` and `fail_closed=true`.

Validation command:

```bash
PYTHONPATH=src python scripts/lint_agents.py
PYTHONPATH=src pytest -q tests/agents/test_step321_initial_agent_contracts.py
```
