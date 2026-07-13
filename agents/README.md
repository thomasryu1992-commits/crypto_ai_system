# Agent Library Contracts

This directory contains review-only markdown contracts for Crypto_AI_System agents.

Agent contracts are governance and instruction artifacts. They are not runtime executors, cannot grant trading permission, and cannot unlock signed testnet or live execution.

Every agent contract must keep:

- `can_modify_runtime: false`
- `can_submit_orders: false`
- evidence-required fail-closed behavior
- explicit prohibited runtime actions
- required output conforming to the declared output schema

Current Step321 scope:

- `approval/approval_intake_validator.md`
- `approval/signed_testnet_unlock_preview_agent.md`
- `risk/kill_switch_auditor.md`
- `risk/hard_cap_reviewer.md`
- `qa/artifact_integrity_auditor.md`

## Step328 Full Agent Role Expansion

Step328 expands the Agent Library from the initial approval/risk/QA contracts into full role-separated review contracts across research, trading, execution, feedback, QA, and approval. These files are markdown contracts only. They do not replace runtime modules and cannot grant signed testnet, live canary, or live scaled permissions.

Required divisions now represented:

- approval: approval intake, signed testnet unlock preview, export packet review
- risk: PreOrderRiskGate audit, kill switch audit, and hard cap review
- qa: artifact integrity, evidence collection, regression runtime hygiene
- research: ResearchSignal building, Signal QA, signal drift review
- trading: decision review, price structure review, permission boundary audit
- execution: paper execution audit, reconciliation audit, order intent chain validation
- feedback: outcome feedback analysis, performance report review, candidate profile review

All contracts must keep `can_modify_runtime=false`, `can_submit_orders=false`, `runtime_mutation_performed=false`, and `order_submission_performed=false`.


## Step328.1 PreOrderRiskGate Auditor Completion

This package adds `agents/risk/preorder_risk_gate_auditor.md` so the Agent Library risk division explicitly covers the full PreOrderRiskGate review boundary. The contract is review-only and cannot mutate runtime settings, submit orders, or unlock signed testnet/live execution.
