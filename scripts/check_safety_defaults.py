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

# Flags that must be falsy by default (fail-closed).
MUST_BE_FALSE = (
    "LIVE_TRADING_ENABLED",
    "ALLOW_LIVE_TRADING",
    "ENABLE_TESTNET_ORDERS",
    "TESTNET_SIGNED_ORDER_ENABLED",
    "LIVE_READONLY_PROBE_ENABLED",
)

# Confirmation gate must be empty by default.
MUST_BE_EMPTY = ("LIVE_TRADING_CONFIRMATION",)


def main() -> int:
    violations: list[str] = []

    for name in MUST_BE_FALSE:
        value = getattr(settings, name, False)
        if value:
            violations.append(f"{name} is enabled by default (got {value!r})")

    for name in MUST_BE_EMPTY:
        value = getattr(settings, name, "")
        if value:
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
