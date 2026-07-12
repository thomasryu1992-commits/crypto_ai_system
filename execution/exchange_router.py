"""Step255 thin compatibility wrapper for `execution.exchange_router`.

Canonical implementation lives in `crypto_ai_system.execution.exchange_router`.
"""

# Step255 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.exchange_router import *  # noqa: F401,F403
