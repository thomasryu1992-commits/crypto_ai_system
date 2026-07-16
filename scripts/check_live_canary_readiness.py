"""Operator readiness check for live canary preparation (read-only).

    py scripts/check_live_canary_readiness.py           # evidence + config only
    py scripts/check_live_canary_readiness.py --probe    # + live read-only probe

Never places, cancels, or transfers anything: the probe client is GET-only by
construction. Writes storage/latest/live_canary_preparation.json and exits
non-zero while any blocker remains. The report is evidence, not authority —
enabling a live canary order is a separate operator-approved step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Load .env before importing config (config reads env at import time).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except Exception:
    pass

import config.settings as settings  # noqa: E402
from collectors.real_market_data import to_binance_symbol  # noqa: E402
from core.json_io import atomic_write_json  # noqa: E402
from crypto_ai_system.execution.live_canary_preparation import (  # noqa: E402
    LiveReadOnlyProbe,
    build_live_canary_preparation_report,
    evaluate_testnet_session_evidence,
    run_live_readonly_probe,
)

SESSION_REPORT_PATH = settings.LATEST_DIR / "signed_testnet_session_report.json"
PREPARATION_REPORT_PATH = settings.LATEST_DIR / "live_canary_preparation.json"


def _load_session_report() -> dict | None:
    if not SESSION_REPORT_PATH.exists():
        return None
    try:
        return json.loads(SESSION_REPORT_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Live canary preparation check.")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="also run the signed GET-only probe against the live venue",
    )
    parser.add_argument("--symbol", default=None, help="override symbol")
    args = parser.parse_args(argv)

    evidence = evaluate_testnet_session_evidence(
        _load_session_report(),
        min_clean_sessions=settings.LIVE_CANARY_MIN_CLEAN_TESTNET_SESSIONS,
    )
    print("=== live canary preparation ===")
    print(f"testnet evidence: {'OK' if evidence['passed'] else 'NOT READY'} "
          f"(clean sessions: {evidence['sessions_ok']}, "
          f"reconcile rate: {evidence['reconcile_rate']})")

    probe_summary = None
    if args.probe:
        if not settings.LIVE_READONLY_PROBE_ENABLED:
            print("probe blocked: LIVE_READONLY_PROBE_ENABLED is false")
            probe_summary = {"ok": False, "errors": ["LIVE_READONLY_PROBE_ENABLED is false"]}
        elif not (settings.LIVE_BINANCE_API_KEY and settings.LIVE_BINANCE_API_SECRET):
            print("probe blocked: LIVE_BINANCE_API_KEY / LIVE_BINANCE_API_SECRET not set")
            probe_summary = {"ok": False, "errors": ["live read-only API keys not set"]}
        else:
            symbol = to_binance_symbol(args.symbol or settings.SYMBOL)
            probe = LiveReadOnlyProbe(
                api_key=settings.LIVE_BINANCE_API_KEY,
                api_secret=settings.LIVE_BINANCE_API_SECRET,
                futures_base_url=settings.LIVE_BINANCE_FUTURES_BASE_URL,
                spot_base_url=settings.LIVE_BINANCE_SPOT_BASE_URL,
            )
            probe_summary = run_live_readonly_probe(probe, symbol)
            print(f"live probe: {'OK' if probe_summary['ok'] else 'FAILED'}")
            if probe_summary["ok"]:
                filters = probe_summary["symbol_filters"]
                print(f"  min notional: {filters.get('min_notional')} | "
                      f"commission taker: {probe_summary['commission'].get('taker')} | "
                      f"open positions: {probe_summary['open_position_count']}")

    report = build_live_canary_preparation_report(
        evidence, probe_summary, probe_attempted=args.probe
    )
    atomic_write_json(PREPARATION_REPORT_PATH, report)
    print(f"report written: {PREPARATION_REPORT_PATH}")

    if report["preparation_ready"]:
        print("preparation READY (order authority remains disabled — separate approval required).")
        return 0
    print("NOT READY:")
    for blocker in report["blockers"]:
        print(f"  - {blocker}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
