"""External P71 read-only account probe.

This package is physically separate from the Crypto_AI_System core because it
may temporarily hold an Extended API key in process memory. It provides GET-only
account evidence and has no signing or write capability.
"""

from .probe import ExtendedPrivateReadOnlyProbe, PrivateReadOnlyProbePolicy

__all__ = ["ExtendedPrivateReadOnlyProbe", "PrivateReadOnlyProbePolicy"]
