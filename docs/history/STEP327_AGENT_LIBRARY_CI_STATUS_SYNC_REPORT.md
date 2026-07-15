# STEP327 Agent Library CI / Status Sync Report

Status: review-only / CI-status-sync complete.

## Scope

Step327 connects the Agent Library governance checks to CI and status consistency validation without changing runtime behavior.

## Added / Modified

- `.github/workflows/review_only_chain_validation.yml`
- `scripts/status_consistency_checker.py`
- `README.md`
- `CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md`
- `tests/agents/test_step327_agent_library_ci_status_sync.py`

## Required CI Commands

```bash
python scripts/lint_agents.py
python scripts/validate_agent_contracts.py
python scripts/validate_agent_outputs.py
python scripts/run_agent_evals.py
python scripts/generate_agent_index.py
python scripts/build_agent_library_contract_review.py
python -m pytest -q tests/agents/
python scripts/status_consistency_checker.py
```

## Safety Result

Agent Library is a review-only contract layer. Agent Library validation does not unlock signed testnet or live execution. Current allowed stage: review-only / shadow / paper-preparation.

Step327 does not mutate `settings.yaml`, does not mutate runtime `score_weights`, does not access API key values, does not access secret files, does not create secret files, does not submit signed testnet/live orders, and does not enable automatic promotion.
