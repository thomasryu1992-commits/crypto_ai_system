# Step264 Report — ResearchSignal Profile Manual Pre-Apply Review Validator

## Summary

Step264 adds a manual pre-apply review validator after the Step263 review-only staging handoff.

It accepts `READY`, `REJECT`, and `REQUEST_MORE_DATA` decisions. `READY` is normalized to `READY_FOR_DISABLED_PRE_APPLY_REVIEW`, but it still cannot apply score weights or mutate runtime settings.

## Added files

```text
src/crypto_ai_system/research/research_signal_profile_pre_apply_review.py
scripts/report_step264_researchsignal_profile_pre_apply_review_validator.py
tests/test_step264_researchsignal_profile_pre_apply_review_validator.py
docs/STEP264_RESEARCHSIGNAL_PROFILE_PRE_APPLY_REVIEW_VALIDATOR.md
```

## Decision behavior

```text
READY + ready Step263 handoff + candidate + passing checklist
→ ready_for_disabled_pre_apply_review

REJECT
→ rejected_pre_apply_review

REQUEST_MORE_DATA
→ more_data_requested

READY + blocked/invalid Step263 handoff
→ invalid
```

## Safety result

```text
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
production_profile_auto_applied = false
config_mutated = false
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
missing_canonical_module_count = 2
```

## Next step

Step265 should create a disabled apply-candidate dry-run packet from a valid Step264 `READY` record while still keeping score-weight mutation disabled.
