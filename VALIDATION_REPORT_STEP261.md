# Validation Report — Step261

## Scope

Step261 creates a manual approval packet for a Step260 review-only ResearchSignal v2 `production_candidate_profile`.

It does not apply selected score weights, mutate runtime settings, enable order routing, or submit external orders.

## Implemented

- Added `research_signal_profile_approval.py`.
- Added Step261 approval packet builder.
- Added approval packet schema validation.
- Added disabled application stub.
- Added Step261 report script.
- Added Step261 documentation and tests.
- Added `research.calibration_approval` config block with hard false apply/write flags.
- Updated project version in `config/settings.yaml`.

## Key files

```text
src/crypto_ai_system/research/research_signal_profile_approval.py
scripts/report_step261_researchsignal_profile_manual_approval_packet.py
tests/test_step261_researchsignal_profile_manual_approval_packet.py
docs/STEP261_RESEARCHSIGNAL_PROFILE_MANUAL_APPROVAL_PACKET.md
STEP261_RESEARCHSIGNAL_PROFILE_MANUAL_APPROVAL_PACKET_REPORT.md
VALIDATION_SUMMARY_STEP261.json
data/reports/step261_researchsignal_profile_manual_approval_packet_report.json
storage/latest/step261_researchsignal_profile_manual_approval_packet_latest.json
```

## Validation commands

```text
pytest tests/test_step261_researchsignal_profile_manual_approval_packet.py -q
# 5 passed

pytest tests/test_step258_feature_store_researchsignal_permission_gate.py \
       tests/test_step259_researchsignal_weight_calibration.py \
       tests/test_step260_researchsignal_profile_review_only_calibration.py \
       tests/test_step261_researchsignal_profile_manual_approval_packet.py -q
# 19 passed

pytest tests/test_step252_thin_wrapper_conversion_plan.py \
       tests/test_step253_thin_wrapper_batch1.py \
       tests/test_step254_missing_canonical_disposition_plan.py \
       tests/test_step255_execution_support_port.py \
       tests/test_step256_paper_research_v1_port.py \
       tests/test_step257_deferred_execution_stub_policy.py \
       tests/test_step258_feature_store_researchsignal_permission_gate.py \
       tests/test_step259_researchsignal_weight_calibration.py \
       tests/test_step260_researchsignal_profile_review_only_calibration.py \
       tests/test_step261_researchsignal_profile_manual_approval_packet.py -q
# 43 passed
```

Additional regression batches:

```text
Step240~251: 30 passed
Step130~164: 40 passed
Step209~219: 37 passed
Step220~237: 59 passed
Plain checkout disabled execution import: passed
```

## Report output

```text
data/reports/step261_researchsignal_profile_manual_approval_packet_report.json
storage/latest/step261_researchsignal_profile_manual_approval_packet_latest.json
```

The clean source handoff does not include stored Feature Store matrices. Therefore, the generated Step261 report uses the Step260 synthetic fallback review and creates a valid packet with:

```text
approval_status = no_candidate_available
candidate_available = false
runtime_score_weights_unchanged = true
application_stub_status = DISABLED_STUB
```

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
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
production_profile_auto_applied = false
```
