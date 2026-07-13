"""Step253 thin compatibility wrapper for `execution.retry_policy`.

Canonical implementation lives in `crypto_ai_system.execution.retry_policy`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.retry_policy import *  # noqa: F401,F403
