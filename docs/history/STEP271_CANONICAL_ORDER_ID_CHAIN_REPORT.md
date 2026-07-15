# Step271 Canonical Decision / RiskGate / OrderIntent ID Chain Report

## Scope

Step271 strengthens the auditable shadow/paper chain by enforcing canonical IDs upstream instead of relying on outcome-time backfill.

Canonical chain:

```text
research_signal_id -> decision_id -> risk_gate_id -> order_intent_id -> execution_id -> reconciliation_id -> outcome_id -> feedback_cycle_id
```

## Safety boundary

Still disabled:

- live trading
- signed testnet order submission
- external exchange order submission
- API key access
- settings.yaml score weight mutation
- automatic runtime profile application
- automatic live/testnet promotion

## Main changes

- Added `src/crypto_ai_system/trading/order_id_chain.py`.
- Updated `research/decision_engine.py` to emit `decision_id`, `research_signal_id`, `profile_id`, `data_snapshot_id`, and `feature_snapshot_id` when ResearchSignal is available.
- Updated `trading/pre_order_risk_gate.py` to block missing canonical upstream IDs.
- Updated `execution/paper_execution_dry_run_bridge.py` so every dry-run order intent has `decision_id`, `risk_gate_id`, `research_signal_id`, `profile_id`, and canonical `order_intent_id`.
- Updated `execution/simulated_paper_order_lifecycle.py` so every lifecycle event and summary carries `execution_id` and `reconciliation_id`.
- Updated `feedback/paper_lifecycle_outcome_store.py` so every outcome carries a complete ID chain including `outcome_id` and `feedback_cycle_id`.
- Added validation checks for canonical ID chain completeness in Step211, Step212, and Step213 validators.
- Added `tests/test_step271_canonical_order_id_chain.py`.

## Compatibility note

Older paper replay artifacts may not contain a true `research_signal_id`. For review-only compatibility, Step211 creates deterministic `research_signal_backfill_*` and `profile_backfill_*` identifiers from Step210 replay evidence. These are marked as review-only backfill metadata and must not be used as live/testnet approval evidence.

## Readiness

Current readiness: **paper possible**.

Not ready for signed testnet or live canary.

## Validation performed

```bash
python -m compileall -q src config tests
```

Result: passed.

```bash
pytest -q tests/test_step271_*.py
```

Result: 4 passed.

```bash
pytest -q tests/test_step211_v5_paper_execution_dry_run_bridge.py tests/test_step212_v5_simulated_paper_order_lifecycle.py tests/test_step213_v5_paper_lifecycle_outcome_store.py tests/test_step270_*.py tests/test_step271_*.py
```

Result: 18 passed.

```bash
pytest -q tests/test_step258_*.py tests/test_step259_*.py tests/test_step260_*.py tests/test_step261_*.py tests/test_step262_*.py tests/test_step263_*.py tests/test_step264_*.py tests/test_step265_*.py tests/test_step266_*.py tests/test_step267_*.py tests/test_step268_*.py tests/test_step269_*.py tests/test_step270_*.py tests/test_step271_*.py
```

Result: 81 passed.

```bash
pytest -q tests/test_step209_237_v5_chain_bootstrap.py tests/test_step211_v5_paper_execution_dry_run_bridge.py tests/test_step212_v5_simulated_paper_order_lifecycle.py tests/test_step213_v5_paper_lifecycle_outcome_store.py tests/test_step270_*.py tests/test_step271_*.py
```

Result: 21 passed.

Full `pytest -q` was attempted but not completed because the container reached the 300 second timeout. No assertion failure was observed before timeout.

## Next recommended step

Step272 should harden paper reconciliation evidence: expected order intent vs simulated execution vs simulated fill vs position delta, fee/slippage model, and mismatch reasons. Live/testnet should remain disabled.
