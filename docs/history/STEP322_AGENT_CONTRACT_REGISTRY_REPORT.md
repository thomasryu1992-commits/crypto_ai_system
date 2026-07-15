# Step322 Agent Contract Registry Report

Status: review-only Agent Contract Registry and index generation added.

Added modules and scripts:

- `src/crypto_ai_system/agents/contract_loader.py`
- `src/crypto_ai_system/registry/agent_contract_registry.py`
- `scripts/lint_agents.py`
- `scripts/validate_agent_contracts.py`
- `scripts/generate_agent_index.py`
- `tests/agents/test_step322_agent_contract_registry.py`

Expected artifacts:

- `storage/latest/agent_lint_report.json`
- `storage/latest/agent_contract_validation_report.json`
- `storage/latest/agent_contract_index.json`
- `storage/latest/agent_contract_registry_record.json`
- `storage/registries/agent_contract_registry.jsonl`

Safety result:

- Registry output is append-only review evidence.
- Registry output is not a runtime permission source.
- Duplicate `agent_id` fails closed.
- Contract file SHA256, body SHA256, and `agent_hash` are recorded.
- Runtime settings mutation, score weight mutation, order submission, and auto-promotion remain disabled.

Validation command:

```bash
PYTHONPATH=src python scripts/generate_agent_index.py
PYTHONPATH=src python scripts/validate_agent_contracts.py
PYTHONPATH=src pytest -q tests/agents/test_step322_agent_contract_registry.py
```
