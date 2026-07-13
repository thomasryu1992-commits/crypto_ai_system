"""Step256 thin compatibility wrapper for `research.dynamic_setup_generator`.

Canonical implementation lives in `crypto_ai_system.research.dynamic_setup_generator`.
"""

# Step256 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.research.dynamic_setup_generator import *  # noqa: F401,F403
