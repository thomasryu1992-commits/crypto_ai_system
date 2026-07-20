"""Fail-closed safety guard.

Asserts that, with no environment overrides, the system cannot place a real
or testnet order: every live/testnet enable flag must be falsy and no
confirmation phrase may be pre-set. This replaces the old multi-hundred-file
"review-only chain" with the single invariant that actually matters.

Exit non-zero if any guard is violated.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings  # noqa: E402

# Sentinel distinct from any real flag value: a renamed/deleted flag must FAIL
# the guard, never pass vacuously via a getattr default.
_MISSING = object()

# Flags that must be falsy by default (fail-closed).
MUST_BE_FALSE = (
    "LIVE_TRADING_ENABLED",
    "ALLOW_LIVE_TRADING",
    "ENABLE_TESTNET_ORDERS",
    "TESTNET_SIGNED_ORDER_ENABLED",
    "EXCHANGE_ORDER_ENABLED",
    "ENABLE_REAL_ORDERS",
    "SIGNED_TESTNET_ADAPTER_CONTRACT_ENABLED",
    "SIGNED_TESTNET_PLACE_ORDER_ENABLED",
    "SIGNED_TESTNET_LIVE_KEY_ALLOWED",
    "LIVE_READONLY_PROBE_ENABLED",
    "STRATEGY_FACTORY_ROUTING_ENABLED",
    "STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED",
    "LIVE_CANARY_ENABLED",
    "LIVE_CANARY_PLACE_ORDER_ENABLED",
    "LIVE_STRATEGY_ORDER_ENABLED",
    "LIVE_STRATEGY_PLACE_ORDER_ENABLED",
)

# Guard rails the fail-closed design depends on: these must stay ON by default.
MUST_BE_TRUE = (
    "SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED",
    "SIGNED_TESTNET_REQUIRE_TESTNET_KEY_SCOPE",
    "LIVE_CANARY_MANUAL_APPROVAL_REQUIRED",
    "BLOCK_SYNTHETIC_DATA_FOR_TRADING",
    "BLOCK_FALLBACK_DATA_FOR_TRADING",
)

# Confirmation gate must be empty by default.
MUST_BE_EMPTY = (
    "LIVE_TRADING_CONFIRMATION",
    "LIVE_CANARY_CONFIRMATION",
    "LIVE_STRATEGY_CONFIRMATION",
)


def main() -> int:
    violations: list[str] = []

    for name in MUST_BE_FALSE:
        value = getattr(settings, name, _MISSING)
        if value is _MISSING:
            violations.append(f"{name} no longer exists in config.settings — guard list is stale")
        elif value:
            violations.append(f"{name} is enabled by default (got {value!r})")

    for name in MUST_BE_TRUE:
        value = getattr(settings, name, _MISSING)
        if value is _MISSING:
            violations.append(f"{name} no longer exists in config.settings — guard list is stale")
        elif not value:
            violations.append(f"{name} is disabled by default (got {value!r}) — this guard rail must stay on")

    for name in MUST_BE_EMPTY:
        value = getattr(settings, name, _MISSING)
        if value is _MISSING:
            violations.append(f"{name} no longer exists in config.settings — guard list is stale")
        elif value:
            violations.append(f"{name} is pre-set by default (got {value!r})")

    if violations:
        print("SAFETY GUARD FAILED:")
        for line in violations:
            print(f"  - {line}")
        return 1

    print("safety defaults OK: no live/testnet order path enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
