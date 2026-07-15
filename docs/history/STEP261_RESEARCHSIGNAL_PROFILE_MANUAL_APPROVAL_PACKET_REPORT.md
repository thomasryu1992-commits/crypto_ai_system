# Step261 Report — ResearchSignal v2 Profile Manual Approval Packet

## Completed

Step261 adds a manual approval packet layer after Step260 review-only calibration.

The system can now:

1. Read or rebuild a Step260 profile review report.
2. Create a Step261 manual approval packet for a review-only `production_candidate_profile`.
3. Preserve candidate profile metadata, normalized weights, matrix source, permission distribution, and review score.
4. Mark the packet as `pending_manual_approval` only when a real Feature Store matrix produced a candidate.
5. Mark the packet as `no_candidate_available` when the matrix is synthetic fallback or no candidate exists.
6. Validate packet schema and safety locks.
7. Expose an application surface only as a disabled stub.
8. Prove runtime `research.score_weights` remain unchanged.

## New module

```text
src/crypto_ai_system/research/research_signal_profile_approval.py
```

Key functions:

```text
resolve_step261_approval_policy()
build_step261_manual_approval_packet()
validate_step261_approval_packet()
apply_step261_approved_profile_disabled_stub()
```

## New report script

```text
scripts/report_step261_researchsignal_profile_manual_approval_packet.py
```

The script can use:

```text
--step260-report existing_report.json
--matrix explicit_feature_store_matrix.csv
```

If no Step260 report exists, it rebuilds a Step260 report. In a clean source checkout without stored Feature Store matrices, this falls back to synthetic validation data, so no candidate is approved for manual review.

## Approval statuses

```text
pending_manual_approval
no_candidate_available
blocked_by_review_policy
```

## Accepted future decisions

```text
APPROVE_FOR_REVIEW_ONLY_STAGING
REJECT
REQUEST_MORE_DATA
```

`APPROVE_FOR_REVIEW_ONLY_STAGING` is not runtime profile application approval.

## Review-only safety locks

```text
auto_apply_approved_profile = false
runtime_score_weight_write_enabled = false
settings_score_weight_write_enabled = false
apply_approved_profile_enabled = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
production_profile_auto_applied = false
config_mutated = false
```

## Execution safety boundary

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
