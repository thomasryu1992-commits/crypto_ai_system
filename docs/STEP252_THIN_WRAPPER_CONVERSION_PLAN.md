# Step252 v5 Thin Wrapper Conversion Plan

## Purpose

Step252 plans conversion of root `execution`, `trading`, and `research` packages into thin compatibility wrappers after direct root imports have been retired.

## Result Type

Plan-only.

Step252 does not convert wrappers and does not delete root package files.

## Added

- `scripts/plan_thin_wrapper_conversion.py`
- `tests/test_step252_thin_wrapper_conversion_plan.py`
- JSON / CSV / Markdown wrapper conversion plan outputs

## Conversion Rule

Only modules with exact canonical counterparts and compatible public exports should be converted first.

Modules without exact canonical counterparts require one of the following before wrapper conversion:

- canonical port
- explicit retirement
- explicit legacy compatibility wrapper decision

## Next Step

Step253 should convert only `READY_FOR_THIN_WRAPPER` modules while leaving missing-canonical modules untouched.
