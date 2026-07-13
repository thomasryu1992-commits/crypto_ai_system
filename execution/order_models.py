"""Step255 thin compatibility wrapper for `execution.order_models`.

Canonical implementation lives in `crypto_ai_system.execution.order_models`.
"""

# Step255 thin wrapper: keep legacy imports working while implementation lives under src/crypto_ai_system.
from crypto_ai_system.execution.order_models import *  # noqa: F401,F403
