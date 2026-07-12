# Step289 — Signal QA Agent Report

## Status

Review-only / paper-safe. Step289 adds an independent Signal QA Agent after ResearchSignal Registry v2 and before downstream decision/risk consumers rely on the signal.

## Implemented

- Added `src/crypto_ai_system/quality/signal_qa.py`.
- Added Signal QA result constants:
  - `PASS_REVIEW_ONLY`
  - `PASS_PAPER_ONLY`
  - `BLOCK_INVALID_LINEAGE`
  - `BLOCK_STALE_DATA`
  - `BLOCK_FALLBACK_OR_SYNTHETIC`
  - `BLOCK_MISSING_SIGNAL`
  - `BLOCK_LEGACY_FALLBACK`
- Added `validate_research_signal_quality()`.
- Added `persist_signal_qa_report()` using append-only `storage/registries/signal_qa_registry.jsonl`.
- Connected `run_raw_to_score_pipeline()` to write:
  - `storage/latest/signal_qa_report.json`
  - `storage/latest/signal_qa_registry_record.json`
  - `storage/registries/signal_qa_registry.jsonl`
- Connected matching Signal QA BLOCK results into `run_research_decision()` so invalid ResearchSignal permission is not authoritative.
- Added `tests/test_step289_signal_qa_agent.py`.
- Added `tests/fixtures/step280_full_regression_runtime_hygiene_report.json` so source handoff tests remain runnable without shipping runtime `data/reports/` evidence.

## Safety Invariants

The step remains review-only. It does not:

- create order intent
- approve trades
- mutate `settings.yaml`
- mutate runtime `score_weights`
- read/create secret files
- access API key values
- submit signed testnet orders
- submit live orders
- promote a profile or execution stage

Runtime flags remain disabled:

- `live_trading_enabled=false`
- `testnet_signed_order_enabled=false`
- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `external_order_submission_allowed=false`
- `external_order_submission_performed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`

## Validation Summary

- `PYTHONPATH=src python -m compileall -q src config tests scripts` — PASSED
- `PYTHONPATH=src pytest -q tests/test_step289_signal_qa_agent.py` — 10 passed
- `PYTHONPATH=src pytest -q tests/test_step282_*.py ... tests/test_step289_*.py` — 35 passed
- `PYTHONPATH=src pytest -q tests/test_step258_*.py ... tests/test_step289_*.py` — 181 passed
- `PYTHONPATH=src python scripts/status_consistency_checker.py` — PASSED
- `PYTHONPATH=src python run_operational_dry_run.py` — PASSED
- `PYTHONPATH=src python run_full_cycle.py` — `BLOCK_DATA_HEALTH / NO_ORDER`
- `run_raw_to_score_pipeline(load_config('.'))` — generated latest Signal QA and registry evidence

## Runtime Evidence

The generated latest Signal QA report showed:

```text
signal_qa_result=PASS_REVIEW_ONLY
allowed_for_decision=true
allowed_for_paper=false
missing_optional_source_count=4
neutral_due_to_missing=true
live_candidate_eligible=false
```

This is expected because optional data sources are missing/disabled and therefore must remain review-only. It is not a signed-testnet/live candidate.

## Next Step

Proceed to Step290 — Legacy Signal Fallback Blocker. Step290 should make legacy fallback paths impossible when `use_research_signal_gate=true` and should turn any attempted legacy path into `BLOCK_LEGACY_FALLBACK` before decision/risk consumption.
