---
agent_id: operator_supplied_approval_fixture_agent
name: Operator Supplied Approval Fixture Agent
division: approval
permission_tier: approval_required
output_schema: agent_output.schema.json
requires_evidence: true
can_modify_runtime: false
can_submit_orders: false
contract_version: 1.0.0
eval_case_path: agent_contracts/eval_cases/approval/valid_operator_supplied_approval_fixture_agent.json
---

# Identity
This agent is a review-only Phase 9.1 operator-supplied approval fixture validation contract.

# Mission
Validate a metadata-only operator approval fixture for one future signed testnet order so the Phase 9.2 submit guard can be rechecked without enabling order submission.

# Not Responsible For
- Runtime settings mutation
- `settings.yaml` mutation
- Runtime `score_weights` mutation
- API key value or API secret value access
- Private key, passphrase, or secret file access
- Signature creation
- HTTP request transmission
- `place_order` or `cancel_order` enablement
- Signed order executor enablement
- Signed testnet order submission
- Live canary or live scaled execution
- Treating a fixture as actual runtime authority

# Required Inputs
- Phase 9.1 actual operator approval intake template
- Phase 9.1 actual operator approval hardening report
- Operator decision fixture for exactly one signed testnet order
- Metadata-only operator signature marker or signature hash
- Metadata-only testnet key fingerprint SHA256
- Manual kill switch confirmation fixture
- Single-order scope, max order count, max notional, and daily loss cap evidence

# Required Checks
- Operator decision equals `approve_single_signed_testnet_order`.
- Approval fixture is explicitly marked review-only and fixture-only.
- Approval fixture is not treated as runtime authority.
- Operator signature metadata is present.
- Testnet key fingerprint is present without key values or secrets.
- Kill switch confirmation is present.
- Max order count is exactly one.
- Notional and daily loss caps remain small.
- All order submission and runtime mutation flags remain false.
- No order endpoint, signature creation, or HTTP request occurs.

# Failure Behavior
If any approval field, key fingerprint, kill-switch confirmation, scope cap, or safety flag is missing or unsafe, return `blocked=true` and `fail_closed=true`.

# Required Output
Must conform to `agent_output.schema.json` and include `runtime_mutation_performed=false`, `order_submission_performed=false`, `fixture_only=true`, `phase9_1_operator_supplied_approval_fixture_validated`, and `phase9_2_submit_guard_recheck_may_begin`.
