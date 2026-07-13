# Step257.1 Plain Checkout / Dependency / Packaging Hotfix Report

## Status

Validated.

## Scope

This hotfix keeps Step257's original execution policy intact while addressing the review findings:

1. `execution.testnet_executor` must import successfully from a plain source checkout without `PYTHONPATH=src` or editable install.
2. Runtime dependencies must be declared in `pyproject.toml` instead of being available only through `requirements.txt`.
3. Source handoff and validation bundle packaging must be clearly separated.

## Changes

### 1. `execution.testnet_executor` self-contained disabled stub

- Removed the dependency on `execution.retry_policy`.
- Added a local `_classify_disabled_stub_recovery_policy()` used only by the disabled testnet compatibility surface.
- Preserved default `TESTNET_ORDER_SKIPPED` behavior.
- Preserved enabled-path `NotImplementedError` behavior.
- Preserved `missing_canonical_module_count == 2`.
- Did not create `src/crypto_ai_system/execution/testnet_executor.py`.
- Did not port live or testnet execution to canonical execution.

### 2. Runtime dependency policy

- Added runtime dependencies to `[project].dependencies` in `pyproject.toml`:
  - `pandas`
  - `numpy`
  - `requests`
  - `python-dotenv`
  - `PyYAML`
  - `tabulate`
- Removed `pytest` from `requirements.txt`.
- Kept `pytest` in `requirements-dev.txt` and `[project.optional-dependencies].dev`.

### 3. Packaging separation

- Clean source handoff remains rooted at `crypto_ai_system_source/`.
- Validation bundle now uses the distinct root `crypto_ai_system_validation/`.
- `build_source_package.py` excludes runtime outputs:
  - `data/reports`
  - `data/stores`
  - `storage/latest`
  - `storage/logs`
  - `storage/tmp`
- `build_audit_bundle.py` now defaults to `dist/crypto_ai_system_validation_bundle.zip`.

## Locked policy retained

```text
missing_canonical_module_count = 2
deferred_modules = ["execution.live_executor", "execution.testnet_executor"]
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
```

## Validation

```text
Step257 focused regression: 7 passed
Step254/256/257 focused regression: 14 passed
Step252~257 regression: 24 passed
Step130~219 regression: 74 passed
Step220~239 regression: 61 passed
Step240~244 individual regression: 8 passed
Step245~251 individual regression: 19 passed
```

Full `pytest` was also attempted, but the execution environment timed out after partial progress. The Step-group regressions above completed successfully.
