"""Step253 thin compatibility wrapper for `execution.live_guard`.

Canonical implementation lives in `crypto_ai_system.execution.live_guard`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.live_guard import *  # noqa: F401,F403
