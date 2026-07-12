# STEP324 Agent Eval Case Runner Report

## Status
Step324 added high-risk Agent Library eval cases and a review-only eval runner.

## Added
- `scripts/run_agent_evals.py`
- `agent_contracts/eval_cases/approval/*.json`
- `agent_contracts/eval_cases/risk/*.json`
- `agent_contracts/eval_cases/qa/*.json`
- `tests/agents/test_step324_agent_eval_case_runner.py`

## Eval Categories
- valid input
- missing required ID
- hash mismatch
- stale data
- fallback/synthetic/sample data
- missing approval packet
- damaged approval file
- prohibited runtime mutation attempt
- broken canonical ID chain

## Safety
Eval execution is review-only. It does not call exchanges, read secrets, mutate runtime settings, enable order submission, or unlock signed testnet/live execution.
