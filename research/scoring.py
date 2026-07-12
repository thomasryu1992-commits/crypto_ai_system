"""Step253 thin compatibility wrapper for `research.scoring`.

Canonical implementation lives in `crypto_ai_system.research.scoring`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.research.scoring import *  # noqa: F401,F403
