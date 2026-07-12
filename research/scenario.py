"""Step253 thin compatibility wrapper for `research.scenario`.

Canonical implementation lives in `crypto_ai_system.research.scenario`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.research.scenario import *  # noqa: F401,F403
