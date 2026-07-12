"""Step256 thin compatibility wrapper for `research.research_decision`.

Canonical implementation lives in `crypto_ai_system.research.research_decision`.
"""

# Step256 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.research.research_decision import *  # noqa: F401,F403
