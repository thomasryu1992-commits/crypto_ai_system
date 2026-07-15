# Validation Report — Step267

## Scope

Step267 validates disabled settings-write preview/export behavior for ResearchSignal v2 profile calibration.

## Commands Run

```bash
PYTHONPATH=src:. python scripts/report_step267_researchsignal_profile_disabled_settings_write_preview.py
PYTHONPATH=src:. python scripts/report_step267_researchsignal_profile_disabled_settings_write_preview.py --matrix tmp_step267_matrix.csv --max-rows 72 --upstream-approval-decision APPROVE_FOR_REVIEW_ONLY_STAGING --upstream-review-decision READY --final-approval-decision APPROVE_DRY_RUN
PYTHONPATH=src:. python run_full_cycle.py
PYTHONPATH=src:. python run_stable_pipeline.py
PYTHONPATH=src:. python run_operational_dry_run.py
PYTHONPATH=src:. python -m pytest -q tests/test_step267_researchsignal_profile_disabled_settings_write_preview.py
PYTHONPATH=src:. python -m pytest -q tests/test_step258_feature_store_researchsignal_permission_gate.py tests/test_step259_researchsignal_weight_calibration.py tests/test_step260_researchsignal_profile_review_only_calibration.py tests/test_step261_researchsignal_profile_manual_approval_packet.py tests/test_step262_researchsignal_profile_approval_intake_validator.py tests/test_step263_researchsignal_profile_review_only_staging_handoff.py tests/test_step264_researchsignal_profile_pre_apply_review_validator.py tests/test_step265_researchsignal_profile_disabled_apply_dry_run.py tests/test_step266_researchsignal_profile_final_apply_approval_validator.py tests/test_step267_researchsignal_profile_disabled_settings_write_preview.py
PYTHONPATH=src:. python -m compileall -q src scripts tests
```

## Results

```text
Step267 focused regression: 5 passed
Step258~267 regression: 52 passed
Step252~257 regression: 24 passed
Step240~244 regression: 11 passed
Step245~251 regression: 19 passed
Operational runner smoke: passed
compileall src/scripts/tests: passed
```

## Safety Result

```text
settings_file_written = false
runtime_score_weights_mutated = false
settings_score_weights_mutated = false
config_mutated = false
external_order_submission_performed = false
real_telegram_send_allowed = false
live_trading_allowed = false
order_routing_enabled = false
```
