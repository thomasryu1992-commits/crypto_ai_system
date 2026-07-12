# Step265 ResearchSignal Profile Disabled Apply Dry Run Report

## Summary

Step265 adds a disabled apply-candidate dry-run packet for ResearchSignal v2 profile calibration. It creates a candidate/current score-weight diff and a hypothetical mutation plan, but the plan is explicitly disabled.

## Implemented

- `research_signal_profile_apply_dry_run.py`
- Step265 report script
- Step265 focused tests
- Config section: `research.calibration_apply_dry_run`
- Documentation and validation artifacts

## Key behavior

- A valid Step264 `READY` record may produce `ready_disabled_apply_dry_run`.
- A default clean-source run without a real candidate remains `blocked_by_pre_apply_review`.
- Candidate weights are reloaded from `research.score_weight_profiles`.
- Current weights are read from `research.score_weights`.
- Diff and mutation plan are generated for review only.
- Mutation plan operations are all disabled.

## Safety boundary

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
missing_canonical_module_count = 2
```
