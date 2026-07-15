# Step325 Agent Library Contract Review Report

## Status
Implemented review-only Agent Library contract review artifact generation.

## Added
- `src/crypto_ai_system/agents/agent_library_contract_review.py`
- `scripts/build_agent_library_contract_review.py`
- `tests/agents/test_step325_agent_library_contract_review.py`

## Behavior
- Reads Agent Library lint, contract validation, registry, output schema validation, and eval evidence from `storage/latest`.
- Produces `agent_library_contract_review_report.json`.
- Produces `agent_permission_policy_report.json`.
- Produces `agent_prohibited_action_scan.json`.
- Appends to `storage/registries/agent_library_contract_review_registry.jsonl`.
- Missing evidence fails closed with `blocked=true` and `fail_closed=true`.

## Safety
- Review-only evidence only.
- Does not mutate runtime settings.
- Does not mutate score weights.
- Does not enable signed testnet or live execution.
- Does not submit orders.
