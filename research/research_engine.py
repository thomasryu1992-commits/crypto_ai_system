"""Step253 thin compatibility wrapper for `research.research_engine`.

Canonical implementation lives in `crypto_ai_system.research.research_engine`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.research.research_engine import *  # noqa: F401,F403
