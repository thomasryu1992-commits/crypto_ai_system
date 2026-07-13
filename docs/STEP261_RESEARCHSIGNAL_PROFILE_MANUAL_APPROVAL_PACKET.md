# Step261 — ResearchSignal Profile Manual Approval Packet

## Purpose

Step261 converts the Step260 review-only `production_candidate_profile` into an auditable manual approval packet.

This step does **not** apply the selected profile to runtime `research.score_weights`.

## Scope

- Create a manual approval packet for the Step260 candidate profile.
- Preserve the candidate profile name, normalized weights, matrix source, permission distribution, and review score.
- Define an approval input schema for a later approval-intake step.
- Lock the profile application surface as a disabled stub.
- Prove that runtime score weights remain unchanged.

## Non-goals

- No automatic profile application.
- No settings mutation.
- No live/testnet order routing.
- No external order submission.
- No root package deletion.

## Approval packet status

When Step260 used a real Feature Store matrix and a candidate passed review thresholds:

```text
approval_status = pending_manual_approval
```

When Step260 used synthetic fallback data or no candidate passed review thresholds:

```text
approval_status = no_candidate_available
```

## Accepted future approval decisions

```text
APPROVE_FOR_REVIEW_ONLY_STAGING
REJECT
REQUEST_MORE_DATA
```

`APPROVE_FOR_REVIEW_ONLY_STAGING` is not runtime application approval. It only authorizes a future review/staging workflow to consider the selected profile.

## Hard safety locks

```text
auto_apply_approved_profile = false
runtime_score_weight_write_enabled = false
settings_score_weight_write_enabled = false
apply_approved_profile_enabled = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
missing_canonical_module_count = 2
```
