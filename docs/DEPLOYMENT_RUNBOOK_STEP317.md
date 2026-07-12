# Step317 Deployment Runbook

Runbook ID: `step317_deployment_runbook_8c0bbb8e349b0421f021f11f`
Status: `DEPLOYMENT_RUNBOOK_REVIEW_ONLY_RECORDED`
Created at UTC: `2026-07-03T04:46:09Z`

This document is review-only. It does not deploy services, start processes, write secret files, mutate settings, submit orders, or promote stages.

## Environment setup

- Use a clean server or container with Python dependencies installed from the locked project package.
- Set APP_ENV to review_only or paper_preparation unless a later signed approval explicitly changes the stage.
- Run compileall and focused regression before any process start is considered.

## Metadata-only secret injection policy

- Store only secret_reference_id, key_fingerprint_sha256, venue, environment, scope, and operator_id metadata.
- Do not write API key values, API secret values, passphrases, or secret files from this runbook.
- Live or testnet key values must never be printed, copied into artifacts, or hashed from raw bytes inside this system.

## Process start / stop procedure

- Start command remains documentation-only until a later explicit deployment approval.
- Stop procedure must terminate the process, preserve logs, and leave kill switch state visible.
- Restart requires a fresh health check, registry integrity check, and operator review.

## Manual kill switch

- The kill switch must fail closed and be checked before testnet/live execution stages.
- A kill switch active state blocks order intent, order submission, and live canary promotion.
- Operator notes must be captured in review-only evidence before any later restart.

## Log paths

- Write runtime health and review evidence under storage/latest and append-only registries under storage/registries.
- Do not store secrets in logs or exception traces.
- Preserve full ID chain references in every operational log summary.

## Backup paths

- Back up source handoff ZIPs, validation bundles, reports, and registries separately.
- Never auto-regenerate missing approval, settings, or source files as a backup strategy.
- Damaged approval or registry evidence must fail closed and be reviewed manually.

## Incident response

- Trigger incident review on API error spikes, reconciliation mismatch, stale data, daily loss breach, or kill switch activation.
- Freeze promotion and order submission until incident evidence is reviewed.
- Record incident summary, root cause, affected IDs, and next action in review-only artifacts.

## Rollback

- Rollback uses prior source handoff ZIP and validation bundle hashes, not ad-hoc file edits.
- Runtime-impacting rollback requires the same manual approval chain as promotion.
- Settings write preview may show rollback diffs, but this runbook must not apply them.

## Daily review

- Review data health, Signal QA, risk gate results, reconciliation blockers, outcome analytics, and monitoring alerts.
- Confirm no external order submission, secret access, or runtime mutation occurred unexpectedly.
- Summarize next action as repeat_in_paper, expand_test_coverage, block_promotion, or archive.

## Disabled runtime guards

- live_trading_enabled, place_order_enabled, cancel_order_enabled, signed_order_executor_enabled, and external_order_submission_allowed remain false.
- settings.yaml mutation, score_weights mutation, and automatic promotion remain disabled.
- This runbook is review-only and does not deploy, start, stop, or mutate runtime services.

## Safety flags

- `api_key_value_access_allowed`: `False`
- `api_secret_value_access_allowed`: `False`
- `auto_promotion_allowed`: `False`
- `cancel_order_enabled`: `False`
- `deployment_execution_enabled`: `False`
- `docker_run_enabled`: `False`
- `env_file_write_enabled`: `False`
- `external_notification_sent`: `False`
- `external_order_submission_allowed`: `False`
- `external_order_submission_performed`: `False`
- `live_order_submission_allowed`: `False`
- `live_trading_enabled`: `False`
- `place_order_enabled`: `False`
- `process_restart_enabled`: `False`
- `process_start_enabled`: `False`
- `process_stop_enabled`: `False`
- `runtime_settings_mutated`: `False`
- `score_weights_mutated`: `False`
- `secret_file_access_allowed`: `False`
- `secret_file_creation_allowed`: `False`
- `secret_injection_metadata_only`: `True`
- `server_deployment_performed`: `False`
- `systemd_write_enabled`: `False`
- `telegram_send_enabled`: `False`

## Block reasons

- None
