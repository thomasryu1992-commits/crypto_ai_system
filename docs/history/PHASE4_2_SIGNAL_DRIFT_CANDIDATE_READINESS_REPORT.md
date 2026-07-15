# Phase 4.2 Signal Drift Review & Candidate Readiness Gate

Phase 4.2 adds a review-only signal-drift analysis and candidate-readiness gate on top of Phase 4.1 paper outcome sample accumulation.

The gate summarizes paper outcomes by direction, regime, regime-direction, timeframe, signal-score bucket, drift bucket, and close reason. Candidate readiness may only use pre-trade dimensions such as direction, regime, regime-direction, and timeframe. Post-outcome labels such as close_reason or result_R are excluded from candidate filtering to avoid leakage.

The current package remains review-only / shadow / paper-preparation. This phase does not create or apply candidate profiles, does not create approval packets, does not mutate settings.yaml, does not mutate runtime score_weights, does not access secrets, does not submit signed testnet/live orders, and does not unlock live execution.

Expected current result on bundled paper outcomes:

```text
PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY
```

The expected blocker is signal-to-outcome drift. Positive expectancy alone is insufficient for candidate profile readiness when drift is still observed.
