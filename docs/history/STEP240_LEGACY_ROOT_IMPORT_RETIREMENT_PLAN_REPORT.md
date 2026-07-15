# Step240 v5 Legacy Root Import Retirement Plan Validation Report

## Scope

Step240 creates a retirement plan for direct imports from root-level `execution`, `trading`, and `research` packages.

This step is plan-only. It does not rewrite imports and does not convert root packages to thin wrappers.

This is not production/live-trading validation.

## Result

- Overall: `PASS`
- compileall `src config tests scripts`: `PASS`
- pytest `tests`: `140 passed`
- legacy root package audit: `PASS`
- import retirement plan generation: `PASS`
- Step209~Step237 chain smoke: `PASS`

## Import Retirement Plan Summary

- direct root import finding count: `29`
- findings by action: `{'MANUAL_MAPPING_REQUIRED': 25, 'READY_FOR_CANONICAL_IMPORT_REWRITE': 4}`
- findings by risk: `{'LOW': 4, 'MEDIUM': 25}`
- rewrite performed: `False`
- wrapper conversion performed: `False`

## Interpretation

Step240 found 4 LOW-risk imports that have exact canonical module paths and 25 MEDIUM-risk imports that require manual mapping before rewrite.

The root packages should not be converted to thin wrappers until the `MANUAL_MAPPING_REQUIRED` rows are resolved.

## Generated Plan Artifacts

```text
data/reports/step240_legacy_root_import_retirement_plan.json
data/reports/step240_legacy_root_import_retirement_plan.csv
data/reports/step240_legacy_root_import_retirement_plan.md
```

## Safety Boundary

Step240 does not enable:

- paper execution
- adapter routing
- external API calls
- Telegram real sends
- live trading

Correct validation label:

`Step209~Step237 chain/artifact-generation validation passed`
