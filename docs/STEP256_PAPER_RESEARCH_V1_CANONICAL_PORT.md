# Step256 v5 Paper/Research Legacy V1 Canonical Port Batch

## Purpose

Step256 ports the remaining paper/report-only legacy v1 modules.

## Ported Modules

- `trading.paper_watch` → `crypto_ai_system.trading.paper_watch`
- `research.dynamic_setup_generator` → `crypto_ai_system.research.dynamic_setup_generator`
- `research.research_cycle` → `crypto_ai_system.research.research_cycle`
- `research.research_decision` → `crypto_ai_system.research.research_decision`

## Root Compatibility

The four root modules are converted into thin re-export wrappers.

## Safety Rule

All modules remain paper/report/decision-only.

They must not enable trading execution, order routing, adapter routing, external API calls, or live trading.

## Expected Result

- `direct_root_import_finding_count` remains `0`.
- `missing_canonical_module_count` decreases from `6` to `2`.
- Remaining missing modules are only `execution.live_executor` and `execution.testnet_executor`.
