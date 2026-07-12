# Step238 v5 Runtime Bootstrap & Packaging Repair

## Purpose

Step238 repairs runtime execution and package hygiene for the Step209~Step237 review-only chain.

## Changes

- Added `scripts.common.bootstrap()` to Step209~Step237 runners.
- Added `requirements-dev.txt`.
- Added `pyproject.toml` with pytest configuration.
- Added GitHub Actions CI workflow.
- Added source/audit package builders.
- Updated README commands.
- Added domain module role table.

## Validation Scope

This is chain/artifact-generation validation only.

It is not production/live-trading validation.
