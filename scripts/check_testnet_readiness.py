"""Operator preflight for signed testnet: verify config, optionally probe auth.

    py scripts/check_testnet_readiness.py           # config-only checks
    py scripts/check_testnet_readiness.py --probe    # + signed read-only balance call

Never places an order. Exits non-zero if not ready.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.signed_testnet_preflight import (  # noqa: E402
    check_config_readiness,
    probe_auth,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signed testnet readiness check.")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="also make a signed read-only balance call to confirm auth",
    )
    args = parser.parse_args(argv)

    readiness = check_config_readiness()
    print("=== signed testnet readiness ===")
    print(f"notional cap: {readiness['notional_cap_usdt']} USDT")
    print(f"daily order cap: {readiness['max_daily_order_count']}")
    if readiness["ready"]:
        print("config: READY")
    else:
        print("config: NOT READY")
        for block in readiness["blocks"]:
            print(f"  - {block}")
        return 1

    if args.probe:
        print("--- signed read-only auth probe ---")
        probe = probe_auth()
        if probe.get("ok"):
            print(f"auth probe: OK (assets={probe.get('assets_returned')}, "
                  f"USDT balance={probe.get('usdt_balance')})")
        else:
            print(f"auth probe: FAILED — {probe.get('error') or probe.get('http_status')}")
            return 1

    print("READY to place a single testnet order (run_testnet_order.py --confirm).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
