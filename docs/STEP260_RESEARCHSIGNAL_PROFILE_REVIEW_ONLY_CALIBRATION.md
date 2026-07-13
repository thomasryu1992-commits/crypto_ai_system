# Step260 — ResearchSignal v2 Profile Review-Only Calibration

## Purpose

Step260 runs ResearchSignal v2 score-weight calibration against a Feature Store matrix and converts the result into a **manual review profile recommendation**.

This step does **not** auto-apply a winning profile. It does **not** mutate runtime score weights. It does **not** enable live/testnet execution.

## Scope

Step260 covers:

- Loading a stored or explicit Feature Store matrix:
  - `storage/features/research_feature_matrix_backtest.csv`
  - `storage/features/research_feature_matrix_live.csv`
  - `storage/features/research_feature_matrix.csv`
  - or a `--matrix` CLI override
- Replaying Step259 weight profiles through ResearchSignal v2 permission logic
- Measuring permission distribution:
  - `normal`
  - `reduced`
  - `blocked`
- Measuring entry permission ratios:
  - `entry_allowed_ratio`
  - `blocked_ratio`
  - `reduced_ratio`
- Ranking candidate profiles using review-only acceptance criteria
- Blocking candidate selection when only synthetic fallback data is available

## Review-only acceptance criteria

Default criteria:

```yaml
research:
  calibration_review:
    mode: review_only
    auto_apply_selected_profile: false
    selected_profile_write_enabled: false
    min_rows: 24
    min_entry_allowed_ratio: 0.03
    max_entry_allowed_ratio: 0.80
    max_blocked_ratio: 0.70
    max_reduced_ratio: 0.60
    target_entry_allowed_ratio: 0.25
    target_blocked_ratio: 0.35
```

Interpretation:

- Too few rows means the profile is not eligible.
- Too many blocked signals means the profile is too restrictive.
- Too many allowed entries means the profile may be too loose.
- Very high reduced-risk ratio is allowed only as a warning.
- Synthetic fallback matrices are never eligible for production candidate selection.

## Production candidate policy

A `production_candidate_profile` may be ranked only when the matrix source type is:

- `stored_feature_store_matrix`, or
- `explicit_feature_store_matrix`

A synthetic fallback matrix can validate code shape but cannot select a candidate.

## Safety boundary

Step260 keeps all execution boundaries closed:

```text
live_trading_allowed = false
order_routing_enabled = false
external_order_submission_performed = false
canonical_live_execution_port_performed = false
canonical_testnet_execution_port_performed = false
root_package_deletion_performed = false
root_package_deletion_deferred = true
missing_canonical_module_count = 2
```

## How to run

Use the stored Feature Store matrix if present:

```bash
python scripts/report_step260_researchsignal_profile_review_only_calibration.py --root .
```

Use an explicit matrix:

```bash
python scripts/report_step260_researchsignal_profile_review_only_calibration.py \
  --root . \
  --matrix storage/features/research_feature_matrix_backtest.csv
```

Optional threshold overrides:

```bash
python scripts/report_step260_researchsignal_profile_review_only_calibration.py \
  --root . \
  --matrix storage/features/research_feature_matrix_backtest.csv \
  --min-rows 100 \
  --max-blocked-ratio 0.65 \
  --target-entry-allowed-ratio 0.20
```

## Output

Default output:

```text
data/reports/step260_researchsignal_profile_review_only_calibration_report.json
```

The output includes:

- matrix source and source type
- rows evaluated
- profile comparison results
- per-profile eligibility review
- review-only candidate profile, if eligible
- proof that no profile was auto-applied
- execution safety boundaries

## Next step

Step261 should connect the review-only candidate into a manual approval packet. Runtime score-weight activation should still remain disabled until explicit approval is implemented and tested.
