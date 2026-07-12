# Step266 Operational Flow Repair

## Purpose

This repair restores the operational runner surface that broke after the `reports.limited_live_readiness` module was removed from the clean source handoff.

The canonical implementation now lives under:

```text
src/crypto_ai_system/reports/limited_live_readiness.py
```

The root package is retained only as a thin compatibility wrapper:

```text
reports/limited_live_readiness.py
```

## Runner Impact

The following runners now import the canonical module directly or continue to work through compatibility:

```text
run_full_cycle.py
run_stable_pipeline.py
run_operational_dry_run.py
run_step150_validation.py
run_limited_live_readiness_report.py
```

## Safety Policy

This repair does not enable live execution, testnet signed orders, real Telegram sends, adapter routing, or config mutation.

Required invariant:

```text
external_order_submission_performed = false
```

## Validation

Required commands:

```bash
PYTHONPATH=src:. python run_full_cycle.py
PYTHONPATH=src:. python run_stable_pipeline.py
PYTHONPATH=src:. python run_operational_dry_run.py
PYTHONPATH=src:. python -m pytest -q tests/test_step258_feature_store_researchsignal_permission_gate.py tests/test_step264_researchsignal_profile_pre_apply_review_validator.py
PYTHONPATH=src:. python -m compileall -q src
```
