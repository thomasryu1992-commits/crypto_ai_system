# Step262 — ResearchSignal Profile Approval-Intake Validator

## Purpose

Step262 adds an approval-intake validator for the Step261 manual approval packet.

This step can record one operator decision:

```text
APPROVE_FOR_REVIEW_ONLY_STAGING
REJECT
REQUEST_MORE_DATA
```

The decision is recorded as an audit artifact only. It does **not** apply the selected profile to runtime `research.score_weights`.

## Scope

- Validate the Step261 approval packet before recording an intake decision.
- Validate required intake fields: `approval_packet_id`, `approval_decision`, `approver`, `rationale`, and `timestamp_utc`.
- Record `APPROVE_FOR_REVIEW_ONLY_STAGING`, `REJECT`, or `REQUEST_MORE_DATA` as a review-only intake artifact.
- Reject approval attempts when no candidate profile is available.
- Keep selected profile application as a disabled stub.

## Decision semantics

```text
APPROVE_FOR_REVIEW_ONLY_STAGING
```

Records that the candidate profile can move into a future review-only staging handoff. It is not runtime approval.

```text
REJECT
```

Records that the candidate profile is rejected.

```text
REQUEST_MORE_DATA
```

Records that more real Feature Store matrix data is required before approval.

## Approval constraints

`APPROVE_FOR_REVIEW_ONLY_STAGING` is only valid when the Step261 packet has:

```text
approval_status = pending_manual_approval
candidate_available = true
```

If Step261 was built from synthetic fallback data or has no production candidate, `APPROVE_FOR_REVIEW_ONLY_STAGING` fails validation.

## Hard safety locks

```text
auto_apply_approved_profile = false
runtime_score_weight_write_enabled = false
settings_score_weight_write_enabled = false
apply_approved_profile_enabled = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
production_profile_auto_applied = false
config_mutated = false
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
missing_canonical_module_count = 2
```

## Non-goals

- No runtime score weight mutation.
- No settings file mutation.
- No automatic profile application.
- No live/testnet order routing.
- No root package deletion.
