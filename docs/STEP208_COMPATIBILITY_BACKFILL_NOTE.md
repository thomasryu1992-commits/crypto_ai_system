# Step208 Compatibility Backfill Note

The uploaded base archive did not include the canonical Step208 dependency modules required by the Step209 runner chain:

- `src/crypto_ai_system/backtest/paper_trading_candidate_registry.py`
- `src/crypto_ai_system/backtest/strategy_matrix_execution.py`

These files are explicitly marked as `compat_stub` backfills. They exist only to make the Step209~237 review-only artifact chain executable and testable from this package.

They are **not** canonical Step208 strategy outputs, not production trading logic, and not evidence that Step208 operational validation passed.

Expected markers:

```text
compatibility_mode = compat_stub
compat_stub = true
canonical_step208_available = false
```

Before using this system beyond artifact-chain validation, replace these compat stubs with the canonical Step208 implementation and rerun the full regression suite.
