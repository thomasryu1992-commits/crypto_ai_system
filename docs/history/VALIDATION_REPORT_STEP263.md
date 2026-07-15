# Validation Report — Step263

## Focused validation

```text
Step263 focused regression: 6 passed
```

## Regression validation

```text
Step258~263 regression: 31 passed
Step252~263 regression: 55 passed
Step240~244 regression: 11 passed
Step245~248 regression: 10 passed
Step249~251 regression: 9 passed
Step209~219 regression: 37 passed
Step220~237 regression: 59 passed
Step130~164 regression: 40 passed
```

## Behavior validated

- Step263 policy hard-locks mutation flags even when overrides try to enable them.
- `REQUEST_MORE_DATA` source intake builds a valid but blocked staging handoff.
- `APPROVE_FOR_REVIEW_ONLY_STAGING` with candidate data creates a `ready_for_pre_apply_review` handoff.
- `REJECT` source intake blocks staging handoff.
- A malformed ready handoff fails validation when candidate/source approval requirements are missing.
- The disabled application stub does not mutate runtime `research.score_weights`.

## Default report state

The clean source package has no real stored Feature Store matrix. Therefore the default Step263 report is intentionally blocked:

```text
handoff_status = blocked_by_approval_intake
ready_for_pre_apply_review = false
candidate_available = false
production_candidate_profile = null
runtime_score_weights_unchanged = true
application_stub_status = DISABLED_STUB
```

## Packaging validation target

The source handoff package must continue to exclude runtime outputs:

```text
data/reports
data/stores
storage
dist
runtime zip/log/cache outputs
```

The validation bundle may include reports and latest outputs under the separate `crypto_ai_system_validation/` root.
