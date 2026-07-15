# Step260 Report — ResearchSignal v2 Profile Review-Only Calibration

## Completed

Step260 adds a review-only calibration layer on top of Step259.

The system can now:

1. Load an explicit or stored Feature Store matrix.
2. Replay ResearchSignal v2 weight profiles.
3. Compare profile-level permission distributions.
4. Evaluate profile eligibility using configurable acceptance criteria.
5. Rank a production candidate profile only when a real Feature Store matrix is supplied.
6. Refuse production candidate selection when only synthetic fallback data is available.
7. Keep all runtime score weights unchanged.
8. Keep live/testnet execution disabled.

## New module functions

```text
resolve_step260_acceptance_criteria()
evaluate_profile_acceptance()
rank_profile_candidates()
build_step260_profile_review()
```

## New report script

```text
scripts/report_step260_researchsignal_profile_review_only_calibration.py
```

The script checks these matrix inputs in order:

```text
--matrix override
storage/features/research_feature_matrix_backtest.csv
storage/features/research_feature_matrix_live.csv
storage/features/research_feature_matrix.csv
synthetic fallback matrix
```

## Review-only policy

```text
auto_apply_selected_profile = false
selected_profile_written_to_settings = false
runtime_score_weights_mutated = false
production_profile_auto_applied = false
config_mutated = false
```

## Candidate policy

A candidate can be ranked only from:

```text
stored_feature_store_matrix
explicit_feature_store_matrix
```

A candidate cannot be selected from:

```text
synthetic_fallback_matrix
```

## Validation result

Focused Step260 tests passed.
Step258/259/260 regression passed.
The plain checkout disabled execution import boundary remains intact.

## Safety boundary

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
