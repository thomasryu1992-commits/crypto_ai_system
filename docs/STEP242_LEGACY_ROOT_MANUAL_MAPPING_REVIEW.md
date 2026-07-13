# Step242 v5 Manual Mapping Review for Legacy Root Imports

## Purpose

Step242 reviews the remaining `MANUAL_MAPPING_REQUIRED` legacy root imports after Step241.

This is a review-only step. It does not rewrite imports and does not convert root packages into thin wrappers.

## Added

- `scripts/review_legacy_root_manual_mappings.py`
- `tests/test_step242_legacy_root_manual_mapping_review.py`
- JSON / CSV / Markdown manual mapping review outputs

## Classification

Each remaining import is classified into one of these actions:

- `READY_FOR_EXACT_CANONICAL_REWRITE_AFTER_TEST`
- `CANONICAL_DOMAIN_SYMBOL_REMAP_REQUIRED`
- `PARTIAL_CANONICAL_PORT_OR_REMAP_REQUIRED`
- `ROOT_ONLY_FEATURE_PORT_REQUIRED`
- `CANONICAL_DOMAIN_MISSING_KEEP_LEGACY`
- `PACKAGE_OR_MODULE_IMPORT_MANUAL_REVIEW`

## Wrapper Conversion Rule

Root `execution`, `trading`, and `research` should not be converted into thin wrappers while unresolved MEDIUM/HIGH blocker rows remain.

## Next Step

Step243 should create a canonical port plan for root-only or partially mapped legacy features.
