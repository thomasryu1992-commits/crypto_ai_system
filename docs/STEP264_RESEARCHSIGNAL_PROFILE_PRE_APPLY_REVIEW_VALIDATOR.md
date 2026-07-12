# Step264 — ResearchSignal Profile Manual Pre-Apply Review Validator

## Purpose

Step264 validates and records a manual pre-apply review decision for a Step263 review-only staging handoff packet.

This step adds a human review checkpoint after `ready_for_pre_apply_review`, but it still does not apply score weights.

## Scope

- Read or rebuild a Step263 staging handoff packet.
- Validate a manual pre-apply review input.
- Record `READY`, `REJECT`, or `REQUEST_MORE_DATA` decisions.
- Treat `READY` as `READY_FOR_DISABLED_PRE_APPLY_REVIEW` internally.
- Keep all runtime and settings mutation surfaces disabled.

## Accepted decisions

```text
READY
REJECT
REQUEST_MORE_DATA
```

`READY` is only valid when the Step263 packet is already `ready_for_pre_apply_review`, has a candidate profile, and has a passing pre-apply checklist.

`READY` does not mean apply now. It records only that the candidate is ready for a later disabled pre-apply dry-run/review step.

## Record status

```text
ready_for_disabled_pre_apply_review
rejected_pre_apply_review
more_data_requested
invalid
```

## READY requirements

A `READY` input is accepted only when all of the following are true:

```text
source_handoff_status = ready_for_pre_apply_review
source_ready_for_pre_apply_review = true
candidate_available = true
production_candidate_profile != null
pre_apply_checklist_summary.all_passed = true
```

If the default clean-source chain has no real Feature Store matrix, Step263 is blocked and Step264 `READY` must fail validation. In that default state, `REQUEST_MORE_DATA` is the expected valid decision.

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
- No testnet/live order routing.
- No root package deletion.
