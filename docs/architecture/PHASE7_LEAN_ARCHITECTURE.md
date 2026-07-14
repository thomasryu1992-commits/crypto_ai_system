# Phase 7 Lean Architecture

## Status

```text
PHASE7_LEAN_MERGE_CLOSED
```

Phase 7 is complete as a review-only, pre-executor governance layer.

It does not enable signed-testnet or live execution.

## Active semantic orchestration

```text
run_executor_review_chain()

↓

run_session_review_chain()

↓

run_executor_approval_chain()

↓

run_stage_transition_chain()

↓

run_pre_executor_review_chain()
```

Canonical modules:

```text
src/crypto_ai_system/governance/
├── executor_review.py
├── session_review.py
├── executor_approval.py
├── stage_transition.py
├── pre_executor_review.py
└── common.py
```

## Semantic implementation steps

Historical Phase-numbered implementations are migrated to:

```text
src/crypto_ai_system/governance/phase7_steps/
├── validation_design.py
├── pre_submit_guard.py
├── review_chain_doctor.py
├── executor_enablement_review.py
├── disabled_executor_review.py
├── disabled_session_reconciliation.py
├── session_close_review.py
├── session_operator_handoff.py
├── executor_prerequisite.py
├── executor_approval_template.py
├── executor_approval_intake.py
├── executor_approval_packet_review.py
├── enablement_design.py
├── enablement_guard_fixtures.py
├── enablement_review.py
└── operator_decision_packet.py
```

The active semantic modules import these paths.

Historical validation paths remain as thin compatibility wrappers.

## Compatibility boundary

Legacy imports remain valid:

```python
from crypto_ai_system.validation.phase7_14_future_executor_operator_decision_packet import (
    persist_phase7_14_future_executor_operator_decision_packet_report,
)
```

The historical file re-exports the semantic implementation.

The wrapper does not contain business logic.

## Shared Governance utilities

Phase 7 reuses and extends:

```text
crypto_ai_system.governance.common
```

Shared contracts include:

```text
latest_dir
storage_dir
read_latest_json
read_optional_json
safe_text
bool_value
number_value
positive_number_within
positive_integer_within
is_zero_number
placeholder_value
canonical_utc_value
hex_fingerprint_valid
artifact_hash
artifact_summary
unsafe_true_fields
unsafe_flags_by_artifact
forbidden_secret_fields
review_only_permission_state
persist_report
```

No separate `phase7_common.py` is created.

## Phase 7.15–7.17

The final intake layer remains directly semantic:

```text
governance/pre_executor_review.py
```

The active orchestration does not import the Phase-numbered 7.15, 7.16, or
7.17 modules. Those historical modules remain temporarily available for the
pre-merge Phase 8 regression suite and compatibility imports; they do not
provide runtime authority.

The manual submission file is never generated automatically.

A missing submission remains:

```text
WAITING_FOR_OPERATOR_DECISION
```

A valid APPROVE decision opens only:

```text
phase8_preparation_design_review_allowed=true
```

It never opens execution.

## Runtime boundary

All of the following remain false:

```text
runtime_permission_source
operator_decision_runtime_authority
stage_transition_authority
executor_enablement_authority
executor_approval_authority
ready_for_signed_testnet_execution
testnet_order_submission_allowed
signed_testnet_promotion_allowed
external_order_submission_allowed
external_order_submission_performed
exchange_endpoint_called
place_order_enabled
cancel_order_enabled
signed_order_executor_enabled
api_key_value_access_allowed
api_secret_value_access_allowed
secret_file_access_allowed
secret_file_creation_allowed
runtime_settings_mutated
auto_promotion_allowed
```

## Next stage

```text
Phase 8
Signed Testnet Execution Preparation
```

Phase 8 may design and dry-validate the final execution boundary.

It still must not submit an order.

The first signed-testnet order remains a separate Phase 9 action after explicit approval.

## Phase 7.15 compatibility migration

Phase 7.15 historical imports remain supported, but the numbered validation
module is now a thin compatibility wrapper.

```text
Historical import:
crypto_ai_system.validation.phase7_15_operator_decision_intake_template

↓

Semantic compatibility contract:
crypto_ai_system.governance.pre_executor_compat.operator_decision_intake
```

`run_full_cycle.py` continues to use only the canonical active orchestration:

```text
crypto_ai_system.governance.pre_executor_review
```

This relocation preserves the Phase 7.15 public API and artifact contract. It
does not grant runtime authority, enable an executor, read secret values, sign
requests, or submit orders.

Phase 7.16 and Phase 7.17 numbered business logic remain temporarily present
and must be migrated in separate reviewed changes.

## Phase 7.16 compatibility migration

Phase 7.16 historical imports remain supported, but the numbered validation
module is now a thin compatibility wrapper.

```text
Historical import:
crypto_ai_system.validation.phase7_16_operator_decision_intake_validator

↓

Semantic compatibility contract:
crypto_ai_system.governance.pre_executor_compat.operator_decision_validation
```

Phase 7.17 consumes the semantic Phase 7.16 contract directly. Active
orchestration remains `crypto_ai_system.governance.pre_executor_review` and
does not import the compatibility package.

The Phase 7.16 export surface is frozen from the module's explicit `__all__`.
This relocation does not change artifact schemas, grant runtime authority,
enable an executor, access secret values, sign requests, or submit orders.

Phase 7.17 numbered business logic remains temporarily present and is the next
migration target.

## Phase 7.15-7.17 numbered business logic retirement

The historical Phase 7.15, 7.16, and 7.17 validation import paths remain
available as thin compatibility wrappers. Their business logic now lives under
the governance compatibility domain:

```text
pre_executor_compat/
├── operator_decision_intake.py
├── operator_decision_validation.py
└── final_pre_executor_review.py
```

Active orchestration continues to use only:

```text
crypto_ai_system.governance.pre_executor_review
```

The compatibility package preserves historical public APIs and artifact
contracts; it is not a runtime authority and is not an alternate orchestration
path.

The numbered business-logic retirement does not enable execution, read secret
values, sign requests, call exchange write endpoints, or submit orders.
