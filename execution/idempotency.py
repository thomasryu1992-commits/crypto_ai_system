"""Step253 thin compatibility wrapper for `execution.idempotency`.

Canonical implementation lives in `crypto_ai_system.execution.idempotency`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.idempotency import *  # noqa: F401,F403
