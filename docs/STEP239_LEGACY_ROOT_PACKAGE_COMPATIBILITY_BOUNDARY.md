# Step239 v5 Legacy Root Package Compatibility Boundary

## Purpose

Step239 prepares the project for P2 package consolidation without breaking existing imports.

The canonical source package is:

`src/crypto_ai_system`

Root-level packages remain temporarily for compatibility:

- `execution`
- `trading`
- `research`

## What Changed

- Root package `__init__.py` files now expose compatibility metadata.
- Added `scripts/audit_legacy_root_packages.py`.
- Added test coverage for legacy package boundary metadata.
- Added this migration document.

## Current Status

`MIGRATION_PENDING`

Root-level `execution`, `trading`, and `research` still contain implementation files. They are not yet thin wrappers.

## Rule

New implementation code should be added under `src/crypto_ai_system`.

Do not add new feature logic to root-level packages.

## Future Step

A later wrapper conversion step should retire direct root imports and convert root modules into thin compatibility wrappers.
