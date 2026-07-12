# Step267 — ResearchSignal Profile Disabled Settings-Write Preview Export

Step267 adds a disabled settings-write preview/export packet for the Step266 final manual approval record.

## Goal

```text
Step266 final approval record
→ disabled settings-write preview/export packet
→ exact config/settings.yaml diff artifact
→ candidate settings.yaml export
→ score_weights mutation and config write remain blocked
```

## Canonical Module

```text
src/crypto_ai_system/research/research_signal_profile_settings_write_preview.py
```

## Report Script

```text
scripts/report_step267_researchsignal_profile_disabled_settings_write_preview.py
```

## Outputs

```text
data/reports/step267_researchsignal_profile_disabled_settings_write_preview_report.json
storage/latest/step267_researchsignal_profile_disabled_settings_write_preview_latest.json
data/reports/step267_settings_write_preview.diff
data/reports/step267_settings_write_preview_candidate_settings.yaml
```

## Preview Statuses

```text
ready_disabled_settings_write_preview
blocked_by_final_apply_approval_record
invalid_source_final_apply_approval_record
```

`ready_disabled_settings_write_preview` requires:

```text
Step266 record_status = approved_disabled_apply_dry_run
Step266 validation valid = true
candidate_available = true
production_candidate_profile != null
candidate_weights_present = true
source mutation plan write/apply disabled
source external_order_submission_performed = false
```

## Hard Locks

Step267 is an export-only stage. It does not write `config/settings.yaml`, mutate runtime `research.score_weights`, enable order routing, send Telegram messages, or activate live/testnet execution.

```text
settings_file_write_enabled = false
settings_file_written = false
config_write_enabled = false
config_mutated = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
live_trading_allowed = false
order_routing_enabled = false
real_telegram_send_allowed = false
external_order_submission_performed = false
```

## Example Commands

Default blocked preview:

```bash
PYTHONPATH=src:. python scripts/report_step267_researchsignal_profile_disabled_settings_write_preview.py
```

Approved disabled dry-run preview path:

```bash
PYTHONPATH=src:. python scripts/report_step267_researchsignal_profile_disabled_settings_write_preview.py \
  --matrix storage/features/research_feature_matrix_backtest.csv \
  --max-rows 72 \
  --upstream-approval-decision APPROVE_FOR_REVIEW_ONLY_STAGING \
  --upstream-review-decision READY \
  --final-approval-decision APPROVE_DRY_RUN
```

## Validation

```bash
PYTHONPATH=src:. python -m pytest -q tests/test_step267_researchsignal_profile_disabled_settings_write_preview.py
PYTHONPATH=src:. python -m compileall -q src scripts tests
```
