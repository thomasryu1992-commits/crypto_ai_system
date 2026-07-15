# Step290 — Legacy Signal Fallback Blocker Report

## Goal

Make the ResearchSignal gate structurally authoritative. When `use_research_signal_gate=true`, legacy research-result or market-snapshot fallback paths must not grant decision, trading signal, paper, signed-testnet, or live permission.

## Files Modified

```text
src/crypto_ai_system/quality/legacy_signal_fallback_blocker.py
src/crypto_ai_system/research/decision_engine.py
src/crypto_ai_system/research/raw_score_pipeline.py
src/crypto_ai_system/trading/signal_engine.py
tests/test_step250_research_engine_port.py
tests/test_step280_full_regression_runtime_hygiene.py
tests/test_step290_legacy_signal_fallback_blocker.py
scripts/status_consistency_checker.py
scripts/run_step280_full_regression.py
.github/workflows/review_only_chain_validation.yml
README.md
CRYPTO_AI_SYSTEM_MASTER_CONTEXT.md
```

## Required Behavior

```text
- Missing ResearchSignal blocks decision/trading permission when the ResearchSignal gate is enabled.
- Missing Signal QA report blocks decision/trading permission when the ResearchSignal gate is enabled.
- Signal QA report must match the ResearchSignal ID.
- Signal QA BLOCK result blocks decision/trading permission.
- legacy_fallback_used / legacy_signal_used / used_legacy_signal markers block permission.
- signal_source=legacy or legacy_fallback blocks permission.
- ALLOW_LEGACY_SIGNAL_FALLBACK cannot reopen trading fallback while the gate is enabled.
```

## Safety Constraints

```text
live_trading_enabled=false
testnet_signed_order_enabled=false
ready_for_signed_testnet_execution=false
testnet_order_submission_allowed=false
external_order_submission_allowed=false
place_order_enabled=false
cancel_order_enabled=false
signed_order_executor_enabled=false
settings mutation disabled
score_weights mutation disabled
automatic promotion disabled
```

## Expected Evidence

```text
storage/latest/legacy_signal_fallback_blocker_report.json
```

## Validation Commands

```text
PYTHONPATH=src python -m compileall -q src config tests
PYTHONPATH=src pytest -q tests/test_step290_*.py
PYTHONPATH=src pytest -q tests/test_step282_*.py tests/test_step283_*.py tests/test_step284_*.py tests/test_step285_*.py tests/test_step286_*.py tests/test_step287_*.py tests/test_step288_*.py tests/test_step289_*.py tests/test_step290_*.py
PYTHONPATH=src pytest -q tests/test_step258_*.py ... tests/test_step290_*.py
PYTHONPATH=src python scripts/status_consistency_checker.py .
PYTHONPATH=src python run_operational_dry_run.py
PYTHONPATH=src python run_full_cycle.py
```

## Acceptance Criteria

```text
- Step290 tests pass.
- Focused Step258~290 regression passes.
- Research decision blocks legacy research_result-only permission while gate is enabled.
- Trading signal blocks legacy fallback even when ALLOW_LEGACY_SIGNAL_FALLBACK is requested.
- Raw pipeline writes legacy_signal_fallback_blocker_report.json.
- All runtime execution flags remain disabled.
```
