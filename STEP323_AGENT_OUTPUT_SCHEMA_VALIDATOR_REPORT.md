# STEP323 Agent Output Schema Validator Report

## Status
Step323 added a review-only Agent Output Schema Validator.

## Added
- `src/crypto_ai_system/agents/agent_output_validator.py`
- `agent_contracts/schemas/agent_output.schema.json`
- agent-specific schema aliases for the initial five high-risk contracts
- `scripts/validate_agent_outputs.py`
- `tests/agents/test_step323_agent_output_schema_validator.py`

## Required Behavior
- Common agent output fields are required.
- `runtime_mutation_performed=true` is blocked fail-closed.
- `order_submission_performed=true` is blocked fail-closed.
- Missing `evidence_hash` is blocked fail-closed.
- Broken canonical ID chain is blocked fail-closed.
- Validation records are review-only and are not runtime permission sources.

## Safety
No settings mutation, score weight mutation, order submission, auto-promotion, signed testnet unlock, live canary unlock, or live scaled unlock is introduced by this step.
