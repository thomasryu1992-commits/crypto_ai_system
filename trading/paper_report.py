"""Step253 thin compatibility wrapper for `trading.paper_report`.

Canonical implementation lives in `crypto_ai_system.trading.paper_report`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.trading.paper_report import *  # noqa: F401,F403
