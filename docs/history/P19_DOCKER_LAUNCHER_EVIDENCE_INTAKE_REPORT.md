# P19 Docker / Launcher Evidence Intake Gate Report

## Status

`P19_DOCKER_LAUNCHER_EVIDENCE_INTAKE_WAITING_REVIEW_ONLY`

P19 adds an external evidence intake gate for Docker build, Docker self-test run, and Launcher import simulation results. This gate does not run Docker, mutate Launcher state, enable schedulers, submit orders, read secrets, or promote runtime permissions.

## Required external evidence files

- `storage/latest/p19_docker_build_evidence_external.json`
- `storage/latest/p19_docker_run_self_test_evidence_external.json`
- `storage/latest/p19_launcher_import_evidence_external.json`

## Current latest status

- `p19_docker_launcher_evidence_intake_valid_review_only=false`
- `docker_build_evidence_valid_review_only=false`
- `docker_run_self_test_evidence_valid_review_only=false`
- `launcher_import_evidence_valid_review_only=false`
- `missing_external_evidence_files=['p19_docker_build_evidence_external.json', 'p19_docker_run_self_test_evidence_external.json', 'p19_launcher_import_evidence_external.json']`

## Safety invariants

- `limited_live_scaled_auto_trading_allowed=false`
- `live_scaled_execution_enabled=false`
- `live_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `runtime_scheduler_enabled=false`
- `runtime_loop_started=false`
- `actual_live_order_submitted=false`
- `live_order_endpoint_called=false`
- `secret_value_accessed=false`

## Operator command

```bash
PYTHONPATH=src:. python scripts/run_docker_launcher_evidence_gate.py
```

To print evidence templates:

```bash
PYTHONPATH=src:. python scripts/run_docker_launcher_evidence_gate.py --print-templates
```

## Negative fixtures

P19 fail-closed fixtures cover missing/blocked P18, failed Docker build, failed Docker self-test run, failed Launcher import, P18 hash mismatch, secret-value pattern leak, endpoint-call evidence, Launcher mutation, and unsafe runtime flags.
