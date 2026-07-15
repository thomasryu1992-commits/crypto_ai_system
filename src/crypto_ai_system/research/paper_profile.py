"""Approved paper-stage profile (B-3).

The real PreOrderRiskGate requires an *approved* profile whose hash matches the
ResearchSignal's. In paper (simulation, no real money) an auto-approved default
profile is appropriate. This profile is scoped to the paper stage only: the
bridge supplies it ONLY when the execution stage is paper. Signed-testnet / live
must obtain approval from a real approved-profile source (none exists yet), so
those stages stay fail-closed at the profile gate.
"""

from __future__ import annotations

from typing import Any

from crypto_ai_system.utils.audit import sha256_json

PAPER_PROFILE_ID = "paper_default_v1"
PAPER_PROFILE_VERSION = "paper_default_v1.0"

# Stable profile content (no timestamps) so the hash is deterministic and the
# ResearchSignal can carry the same profile_sha256 for the gate's hash check.
_PAPER_PROFILE_CORE: dict[str, Any] = {
    "profile_id": PAPER_PROFILE_ID,
    "profile_version": PAPER_PROFILE_VERSION,
    "approved": True,
    "approval_status": "approved",
    "stage": "paper",
    "approved_stages": ["paper"],
}

PAPER_PROFILE_SHA256 = sha256_json(_PAPER_PROFILE_CORE)


def get_paper_profile() -> dict[str, Any]:
    """Return the approved paper profile (approved for the paper stage only)."""
    profile = dict(_PAPER_PROFILE_CORE)
    profile["profile_sha256"] = PAPER_PROFILE_SHA256
    profile["profile_hash"] = PAPER_PROFILE_SHA256
    return profile
