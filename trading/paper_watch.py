"""Step256 thin compatibility wrapper for `trading.paper_watch`.

Canonical implementation lives in `crypto_ai_system.trading.paper_watch`.
"""

# Step256 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.trading.paper_watch import *  # noqa: F401,F403
