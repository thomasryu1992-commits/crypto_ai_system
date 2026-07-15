# Validation Report — Step265

## Scope

Step265 adds a disabled apply-candidate dry-run packet for ResearchSignal v2 profile calibration.

## Validated behavior

- Step265 can build a dry-run packet from a Step264 pre-apply review record.
- Default clean-source run without an approved candidate remains blocked by pre-apply review.
- Valid Step264 READY record can produce `ready_disabled_apply_dry_run`.
- Candidate profile weights are reloaded from `research.score_weight_profiles`.
- Current runtime settings are read from `research.score_weights`.
- Candidate/current settings diff is produced.
- Mutation plan is created but all operations are disabled.
- Runtime score weights and settings remain unchanged.
- Execution boundary remains closed.

## Test results

```text
Step265 focused regression: 5 passed
Step264 + Step265 focused regression: 11 passed
Step258~265 regression: 42 passed
Step252~265 regression: 66 passed
Step240~244 regression: 11 passed
Step245~248 regression: 10 passed
Step249~251 regression: 9 passed
Step209~219 regression: 34 passed
Step220~237 regression: 54 passed
Step130~164 regression: 40 passed
```

## Safety status

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
