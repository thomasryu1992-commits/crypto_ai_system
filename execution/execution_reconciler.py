"""Step253 thin compatibility wrapper for `execution.execution_reconciler`.

Canonical implementation lives in `crypto_ai_system.execution.execution_reconciler`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.execution_reconciler import *  # noqa: F401,F403
