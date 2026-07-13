# Step259 ResearchSignal Weight Calibration Report

## Status

Completed.

## Implemented

- Added `crypto_ai_system.research.research_signal_calibration`.
- Added normalized ResearchSignal v2 score-weight profile comparison.
- Added permission distribution reporting for `normal / reduced / blocked` outcomes.
- Added side distribution reporting for `LONG / SHORT / FLAT` outcomes.
- Added Telegram extra-data summary section in both canonical notifier and root Telegram summary builder.
- Added Step259 report builder script.
- Preserved Step257 deferred execution stub policy and Step258 permission gate boundaries.

## New calibration module

```text
src/crypto_ai_system/research/research_signal_calibration.py
```

Main entry points:

```text
normalize_score_weights()
resolve_weight_profiles()
evaluate_weight_profile_on_matrix()
compare_weight_profiles()
```

## New report script

```text
scripts/report_step259_researchsignal_weight_calibration.py
```

The script reads an available Feature Store matrix if present. If no runtime matrix exists in the source handoff package, it uses a deterministic synthetic calibration matrix so the report remains reproducible in clean checkout environments.

## Version updates

```text
project.version = step259_researchsignal_weight_calibration_permission_distribution
ResearchSignal v2 = research_signal_v2_step259_weight_calibration_permission_distribution
Feature matrix = step259_weight_calibration_permission_distribution_matrix
Calibration = step259_researchsignal_weight_calibration_v1
```

## Validation summary

Focused validation passed:

```text
tests/test_step259_researchsignal_weight_calibration.py: 5 passed
tests/test_step258_feature_store_researchsignal_permission_gate.py: 3 passed
combined Step258/259 focused regression: 8 passed
```

## Safety result

No live execution was enabled or ported.

```text
missing_canonical_module_count = 2
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
```
