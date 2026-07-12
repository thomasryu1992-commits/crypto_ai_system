from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import (
    build_submit_intent_from_env_and_args,
    persist_phase9_2_single_testnet_runtime_submit_wrapper,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 9.2 single testnet runtime submit wrapper. Mocked by default.")
    parser.add_argument("--confirm-real-testnet-submit", action="store_true", help="Required for mock-submit readiness; does not enable real endpoint calls in this package.")
    parser.add_argument("--approval-text", default="", help="Explicit operator approval text. Do not include secrets.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", default="BUY")
    parser.add_argument("--order-type", default="MARKET")
    parser.add_argument("--quantity", default="0.001")
    parser.add_argument("--max-notional", type=float, default=10.0)
    parser.add_argument("--key-ref", default="metadata_only_testnet_key_ref")
    parser.add_argument("--key-fingerprint-sha256", default="")
    parser.add_argument("--fresh-risk-refresh-passed", action="store_true")
    parser.add_argument("--kill-switch-confirmed", action="store_true")
    parser.add_argument("--no-mock-submit", action="store_true", help="Generate dry-run report only.")
    args = parser.parse_args()

    intent = build_submit_intent_from_env_and_args(
        symbol=args.symbol,
        side=args.side,
        order_type=args.order_type,
        quantity=args.quantity,
        max_notional=args.max_notional,
        approval_text=args.approval_text,
        key_ref=args.key_ref,
        key_fingerprint_sha256=args.key_fingerprint_sha256,
        confirm_real_testnet_submit=args.confirm_real_testnet_submit,
        allow_mock_submit=not args.no_mock_submit,
        fresh_endpoint_time_risk_refresh_passed=args.fresh_risk_refresh_passed,
        kill_switch_confirmed=args.kill_switch_confirmed,
    )
    report = persist_phase9_2_single_testnet_runtime_submit_wrapper(intent=intent)
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "mock_order_submission_performed": report["mock_order_submission_performed"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
