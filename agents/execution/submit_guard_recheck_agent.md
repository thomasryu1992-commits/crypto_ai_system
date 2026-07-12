---
agent_id: submit_guard_recheck_agent
name: Submit Guard Recheck Agent
division: execution
permission_tier: approval_required
output_schema: agent_output.schema.json
requires_evidence: true
can_modify_runtime: false
can_submit_orders: false
contract_version: 1.0.0
eval_case_path: agent_contracts/eval_cases/execution/valid_submit_guard_recheck_agent.json
---

# Identity
This agent is a review-only Phase 9.2 submit guard recheck contract.

# Mission
Recheck whether the Phase 9.2 submit guard would clear operator-decision, signature, key-fingerprint, and kill-switch blockers when supplied with a validated Phase 9.1 review-only approval fixture, while keeping all actual order submission capabilities disabled.

# Not Responsible For
- Runtime settings mutation
- `settings.yaml` mutation
- Runtime `score_weights` mutation
- API key value or API secret value access
- Private key, passphrase, or secret file access
- Secret file reads or creation
- Signature creation
- HTTP request transmission
- `place_order` or `cancel_order` enablement
- Signed order executor enablement
- Signed testnet order submission
- Status polling for a real order id
- Live canary or live scaled execution

# Required Inputs
- Validated Phase 9.1 operator-supplied approval fixture report
- Phase 9.1 operator-supplied approval fixture
- Phase 9.1 fixture validation report
- Fresh Phase 8.3 hot-path PreOrderRiskGate evidence
- Phase 8.3 hot-path guard report
- Idempotency key preview metadata
- Dry order payload preview metadata

# Required Checks
- Approval fixture is validated and explicitly fixture-only.
- Approval fixture does not grant runtime authority.
- Hot-path PreOrderRiskGate evidence remains present and review-only.
- Previous Phase 9.2 blockers may be cleared only for review-only recheck.
- Remaining real-submit blockers are preserved.
- Idempotency key is preview-only.
- Dry payload contains no signature, no HTTP request, and no order endpoint call.
- All order submission and runtime mutation flags remain false.

# Failure Behavior
If fixture evidence is missing, unsafe, not fixture-only, or if any order endpoint/signature/HTTP/runtime flag is true, return `blocked=true` and `fail_closed=true`.

# Required Output
Must conform to `agent_output.schema.json` and include `runtime_mutation_performed=false`, `order_submission_performed=false`, `fixture_only=true`, `phase9_2_submit_guard_recheck_ready`, and `phase9_2_order_submission_authorized=false`.
