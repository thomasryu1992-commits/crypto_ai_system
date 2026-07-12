# Domain Module Role Table — Step238

## Canonical Package

New implementation code should use:

`src/crypto_ai_system`

## Module Roles

| Domain | Canonical location | Legacy/root location | Current role | Status |
|---|---|---|---|---|
| execution | `src/crypto_ai_system/execution` | `execution` | mixed legacy/current | wrapper migration pending |
| trading | `src/crypto_ai_system/trading` | `trading` | mixed legacy/current | wrapper migration pending |
| research | `src/crypto_ai_system/research` | `research` | mixed legacy/current | wrapper migration pending |
| backtest | `src/crypto_ai_system/backtest` | legacy references | Step208 compat + Step209+ chain | canonical for current chain |
| ops | `src/crypto_ai_system/ops` | N/A | Step217+ review-only gates | canonical |
| scripts | `scripts` | N/A | bootstrap/package helpers | utility |

## Rule

Do not add new feature logic to root-level `execution`, `trading`, or `research`.
A future refactor should convert root modules into thin compatibility wrappers.


## Step239 Boundary Update

Root-level `execution`, `trading`, and `research` package `__init__.py` files are now explicitly marked as legacy compatibility packages.

The migration status remains:

`wrapper_migration_pending`

This step does not remove legacy modules. It establishes guardrails and audit visibility before wrapper conversion.
