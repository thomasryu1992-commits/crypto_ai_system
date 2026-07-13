# Step266 — ResearchSignal Profile Final Apply Approval Validator

## Scope

Step266 adds a final manual apply approval validator for the Step265 disabled apply-candidate dry-run packet.

This step records one of three operator decisions:

```text
APPROVE_DRY_RUN
REJECT
REQUEST_MORE_DATA
```

`APPROVE_DRY_RUN` means only that the Step265 disabled dry-run packet has passed final manual review. It does not apply the candidate profile, write `research.score_weights`, mutate runtime weights, or enable execution.

## Source Dependency

Step266 consumes either:

```text
apply_dry_run_packet
```

from a Step265 report, or a direct Step265 dry-run packet.

When no Step265 report exists, the Step266 report script can rebuild the upstream Step260~265 chain. In a clean source handoff without a stored Feature Store matrix, the default path requests more data and remains blocked from approval.

## Approval Rules

`APPROVE_DRY_RUN` is valid only when all of the following are true:

```text
source_dry_run_status = ready_disabled_apply_dry_run
source_ready_for_disabled_apply_dry_run = true
candidate_available = true
production_candidate_profile != null
candidate_weights_present = true
mutation_plan_write_enabled = false
mutation_plan_apply_enabled = false
```

If any of these fail, `APPROVE_DRY_RUN` produces an invalid record and the report fails validation.

`REJECT` and `REQUEST_MORE_DATA` are valid record decisions even when the source dry-run is blocked.

## Non-Mutation Boundary

The following values remain hard-locked:

```text
auto_apply_approved_profile = false
runtime_score_weight_write_enabled = false
settings_score_weight_write_enabled = false
apply_approved_profile_enabled = false
candidate_profile_applied = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
config_mutated = false
```

## Execution Boundary

Step266 does not modify the execution surface.

```text
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
missing_canonical_module_count = 2
```

## Commands

Default clean-source report:

```bash
python scripts/report_step266_researchsignal_profile_final_apply_approval_validator.py
```

Ready dry-run approval path with explicit matrix:

```bash
python scripts/report_step266_researchsignal_profile_final_apply_approval_validator.py \
  --matrix storage/features/research_feature_matrix_backtest.csv \
  --max-rows 72 \
  --upstream-approval-decision APPROVE_FOR_REVIEW_ONLY_STAGING \
  --upstream-review-decision READY \
  --final-approval-decision APPROVE_DRY_RUN
```

Focused tests:

```bash
python -m pytest -q tests/test_step266_researchsignal_profile_final_apply_approval_validator.py
```

## Output Artifacts

```text
data/reports/step266_researchsignal_profile_final_apply_approval_validator_report.json
storage/latest/step266_researchsignal_profile_final_apply_approval_validator_latest.json
```
