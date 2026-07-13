# Step265 — ResearchSignal Profile Disabled Apply-Candidate Dry Run

## Purpose

Step265 converts a valid Step264 `READY` pre-apply review record into a dry-run apply packet. The packet compares the candidate profile weights against the current `research.score_weights` and produces a hypothetical mutation plan.

This step is still review-only. It must not write `settings.yaml`, mutate runtime score weights, enable live/testnet routing, or submit orders.

## Scope

- Load or rebuild the Step264 pre-apply review record.
- Require `record_status = ready_for_disabled_pre_apply_review` before a dry-run can be ready.
- Reload candidate profile weights from `research.score_weight_profiles` using `production_candidate_profile`.
- Compare candidate weights with current `research.score_weights`.
- Produce a disabled mutation plan.
- Keep all write/apply behavior disabled.

## Dry-run statuses

- `ready_disabled_apply_dry_run`
- `blocked_by_pre_apply_review`
- `invalid_source_pre_apply_review`

## Safety locks

The following values are hard locked in code and cannot be enabled by config override:

```text
auto_apply_candidate_profile = false
runtime_score_weight_write_enabled = false
settings_score_weight_write_enabled = false
apply_candidate_profile_enabled = false
```

## Non-goals

- No score-weight mutation.
- No settings write.
- No production profile activation.
- No live/testnet execution port.
- No root package deletion.

## Next step

Step266 should add a final manual approval validator for the Step265 dry-run packet while keeping actual mutation disabled.
