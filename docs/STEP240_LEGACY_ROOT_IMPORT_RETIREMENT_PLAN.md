# Step240 v5 Legacy Root Import Retirement Plan

## Purpose

Step240 creates a plan for retiring direct imports from root-level `execution`, `trading`, and `research`.

This step does not rewrite imports and does not convert root packages into thin wrappers.

## Added

- `scripts/plan_legacy_root_import_retirement.py`
- `tests/test_step240_legacy_root_import_retirement_plan.py`
- Step240 import retirement JSON/CSV/Markdown report generation

## Classification

The planner classifies each root import into one of these actions:

- `READY_FOR_CANONICAL_IMPORT_REWRITE`
- `READY_FOR_PACKAGE_LEVEL_CANONICAL_IMPORT_REWRITE`
- `MANUAL_MAPPING_REQUIRED`
- `KEEP_LEGACY_TEMPORARY`

## Safety

Step240 is plan-only.

It does not enable:

- paper execution
- adapter routing
- external API calls
- Telegram real sends
- live trading

## Next Step

Step241 should rewrite only LOW-risk exact canonical import candidates first, then rerun the full test suite.
