# Step263 — ResearchSignal Profile Review-Only Staging Handoff

## Purpose

Step263 creates a review-only staging handoff packet from a valid Step262 approval-intake record.

This step exists to move an `APPROVE_FOR_REVIEW_ONLY_STAGING` decision into a pre-apply review artifact without applying score weights.

## Scope

- Read or rebuild a Step262 approval-intake record.
- Validate that the source decision is `APPROVE_FOR_REVIEW_ONLY_STAGING`.
- Create a staging handoff packet only when the source record is valid and candidate-backed.
- Add a pre-apply checklist and schema for a later manual review step.
- Keep all score-weight application surfaces disabled.

## Handoff status

```text
ready_for_pre_apply_review
blocked_by_approval_intake
invalid_source_intake
```

`ready_for_pre_apply_review` is only possible when the source Step262 record has:

```text
approval_decision = APPROVE_FOR_REVIEW_ONLY_STAGING
record_status = accepted_review_only_staging
recorded = true
candidate_available = true
production_candidate_profile != null
```

`blocked_by_approval_intake` is expected when the source decision is `REQUEST_MORE_DATA` or `REJECT`, or when no candidate profile is available.

`invalid_source_intake` is used when the Step262 record itself fails validation.

## Pre-apply checklist

The Step263 handoff packet includes a checklist for the next review layer:

```text
source_step262_intake_valid
approval_intake_is_review_only_staging
candidate_profile_available
candidate_weights_present_or_deferred
manual_pre_apply_review_required
runtime_score_weight_write_disabled
settings_score_weight_write_disabled
execution_routing_disabled
```

This checklist is a gate for human review only. It does not enable runtime mutation.

## Hard safety locks

```text
auto_apply_selected_profile = false
selected_profile_written_to_settings = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
production_profile_auto_applied = false
config_mutated = false
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
missing_canonical_module_count = 2
```

## Non-goals

- No runtime `research.score_weights` mutation.
- No `settings.yaml` mutation.
- No automatic application of the selected profile.
- No live/testnet order routing.
- No root package deletion.
