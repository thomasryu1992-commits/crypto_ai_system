"""Step255 thin compatibility wrapper for `execution.mock_exchange`.

Canonical implementation lives in `crypto_ai_system.execution.mock_exchange`.
"""

# Step255 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.mock_exchange import *  # noqa: F401,F403
