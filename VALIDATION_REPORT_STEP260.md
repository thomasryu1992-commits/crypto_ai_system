# Validation Report — Step260

## Scope

Step260 adds review-only ResearchSignal v2 score-weight profile calibration against Feature Store matrices.

It does not auto-apply a selected profile, mutate runtime score weights, write a selected profile into config, or enable order routing.

## Implemented

- Added Step260 acceptance criteria resolver.
- Added per-profile eligibility review.
- Added candidate ranking for manual review only.
- Added production candidate policy requiring a real Feature Store matrix.
- Added synthetic fallback protection: synthetic matrix can validate code shape but cannot select a candidate profile.
- Added Step260 report script.
- Added Step260 documentation and tests.
- Updated project version in `config/settings.yaml`.

## Key files

```text
src/crypto_ai_system/research/research_signal_calibration.py
scripts/report_step260_researchsignal_profile_review_only_calibration.py
tests/test_step260_researchsignal_profile_review_only_calibration.py
docs/STEP260_RESEARCHSIGNAL_PROFILE_REVIEW_ONLY_CALIBRATION.md
STEP260_RESEARCHSIGNAL_PROFILE_REVIEW_ONLY_CALIBRATION_REPORT.md
VALIDATION_SUMMARY_STEP260.json
data/reports/step260_researchsignal_profile_review_only_calibration_report.json
```

## Validation commands

```text
pytest tests/test_step260_researchsignal_profile_review_only_calibration.py -q
# 6 passed

pytest tests/test_step258_feature_store_researchsignal_permission_gate.py \
       tests/test_step259_researchsignal_weight_calibration.py \
       tests/test_step260_researchsignal_profile_review_only_calibration.py -q
# 14 passed

pytest tests/test_step252_thin_wrapper_conversion_plan.py \
       tests/test_step253_thin_wrapper_batch1.py \
       tests/test_step254_missing_canonical_disposition_plan.py \
       tests/test_step255_execution_support_port.py \
       tests/test_step256_paper_research_v1_port.py \
       tests/test_step257_deferred_execution_stub_policy.py \
       tests/test_step258_feature_store_researchsignal_permission_gate.py \
       tests/test_step259_researchsignal_weight_calibration.py \
       tests/test_step260_researchsignal_profile_review_only_calibration.py -q
# 38 passed
```

Additional regression batches:

```text
Step240~244: 11 passed
Step245~248: 10 passed
Step249: 3 passed
Step250: 3 passed
Step251: 3 passed
Step209~219: 37 passed
Step220~237: 59 passed
Step130~164: 40 passed
```

## Report output

```text
data/reports/step260_researchsignal_profile_review_only_calibration_report.json
```

The clean source handoff does not include runtime Feature Store files, so the generated report uses the synthetic fallback matrix. Because the source type is `synthetic_fallback_matrix`, no production candidate profile is selected.

## Safety boundaries

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
