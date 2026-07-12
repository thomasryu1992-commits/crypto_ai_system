"""Step253 thin compatibility wrapper for `execution.order_executor`.

Canonical implementation lives in `crypto_ai_system.execution.order_executor`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.order_executor import *  # noqa: F401,F403
