# Step297 — Performance Report Generator Report

## Goal

Add a review-only performance report generator after Step296 Outcome Analytics v2. The report aggregates outcome feedback records and prepares evidence for later candidate profile review without applying any runtime changes.

## Implemented

- Added `src/crypto_ai_system/feedback/performance_report_generator.py`.
- Added append-only `performance_report_registry.jsonl` support through the canonical registry layer.
- Added latest evidence files:
  - `storage/latest/performance_report.json`
  - `storage/latest/performance_report_registry_record.json`
- Connected `run_full_cycle.py` to run performance reporting after outcome analytics.
- Connected `run_operational_dry_run.py` to expose `performance_report_status`.
- Added Step297 focused tests.

## Metrics Tracked

- sample size
- expectancy
- win/loss ratio
- average_R
- max_drawdown
- R distribution
- slippage
- latency
- rejection rate
- stale data rate
- signal-to-outcome drift
- paper/live gap
- API error rate
- manual override count
- failure modes
- recommendation

## Safety

Step297 is review-only. It does not create candidate profiles, approval packets, runtime settings mutations, score weight mutations, signed testnet orders, live orders, or automatic promotion.

## Next Step

Step298 — Candidate Profile Registry.
