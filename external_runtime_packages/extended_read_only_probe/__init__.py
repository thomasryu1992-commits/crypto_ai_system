"""External P71 credential-bearing read-only probe.

The package may temporarily hold an Extended API key in its own process memory.
It exposes GET-only private REST and authenticated private account-stream
connectivity. It has no signer, no Stark private-key access, and no write method.
"""

from .probe import (
    ExtendedPrivateReadOnlyProbe,
    PrivateReadOnlyProbePolicy,
    resolve_private_stream_endpoints,
    websocket_private_account_snapshot_probe,
)

__all__ = [
    "ExtendedPrivateReadOnlyProbe",
    "PrivateReadOnlyProbePolicy",
    "resolve_private_stream_endpoints",
    "websocket_private_account_snapshot_probe",
]
