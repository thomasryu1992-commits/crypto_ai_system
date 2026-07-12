"""Step253 thin compatibility wrapper for `trading.permission_audit`.

Canonical implementation lives in `crypto_ai_system.trading.permission_audit`.
"""

# Step253 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.trading.permission_audit import *  # noqa: F401,F403
