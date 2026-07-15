# Step237 Hardening 6~9 Validation Report

## Status

`PASS`

Validation wording remains: `체인/산출물 생성 검증 통과`.

This package still does **not** claim operating validation, production/live trading validation, live exchange adapter validation, real Telegram send validation, or live order execution validation.

## Changes Applied

1. Step208 compatibility backfill is explicitly marked as `compat_stub`.
   - Added `STEP208_COMPATIBILITY_MODE = "compat_stub"`.
   - Step208 result payload now includes `compatibility_mode`, `compat_stub`, `canonical_step208_available`, and `compatibility_scope`.
   - Stub-generated registry IDs are prefixed with `compat_stub_`.

2. Fallback data profile separation.
   - Added `config/fallback_data_profiles.yaml`.
   - `load_config()` loads fallback profiles into `fallback_data_profiles`.
   - Active fallback profile is selected through `data.fallback_profile` / `FALLBACK_DATA_PROFILE`.
   - Fallback profiles are marked `RESEARCH_BACKTEST_ONLY` and `allow_live_execution: false`.

3. `settings.py` import side effects removed.
   - No import-time dotenv loading.
   - No import-time runtime directory creation.
   - No import-time live-trading confirmation exception.
   - Added explicit runtime functions: `load_project_dotenv()`, `ensure_runtime_directories()`, and `validate_live_trading_confirmation()`.

4. `tmp_path` test isolation strengthened.
   - Added `tests/conftest.py` with `isolated_project_root` fixture.
   - Step209~237 tests now write generated artifacts under `tmp_path`, not the package root.
   - Added targeted tests for compat_stub, fallback profiles, settings side-effect behavior, and tmp-path artifact isolation.

## Validation Commands

```text
python -m compileall -q src config tests
PASS

python run_step209_237_v5_chain_bootstrap.py
STEP209_237_V5_CHAIN_BOOTSTRAP_OK
runner_count_expected: 29
runner_count_executed: 29
runner_count_passed: 29
runner_count_failed: 0

pytest -q tests
136 passed in 20.60s
```

## Boundary

The result confirms the Step209~237 review-only chain and artifact generation behavior. It does not validate real API responses, real exchange order routing, live order lifecycle, production deployment, or strategy profitability.
