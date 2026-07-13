# Validation Report Step259

## Scope

ResearchSignal v2 weight calibration, permission distribution reporting, and Telegram extra-data summary integration.

## Result

Passed focused validation.

## Commands executed

```text
pytest -q tests/test_step259_researchsignal_weight_calibration.py
pytest -q tests/test_step258_feature_store_researchsignal_permission_gate.py tests/test_step259_researchsignal_weight_calibration.py
python scripts/report_step259_researchsignal_weight_calibration.py --root . --max-rows 48
```

## Test results

```text
tests/test_step259_researchsignal_weight_calibration.py: 5 passed
Step258 + Step259 focused regression: 8 passed
Step252~259 regression: 32 passed
Step240~251 regression: 30 passed
Step130~164 regression: 40 passed
Step209~237 regression: 96 passed
```

## Report output

```text
data/reports/step259_researchsignal_weight_calibration_report.json
```

## Safety checks

```text
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
missing_canonical_module_count = 2
```
