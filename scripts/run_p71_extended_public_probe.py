from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.execution.extended_read_only_connectivity import run_p71_public_probe


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run P71 Extended testnet public GET-only REST and public WebSocket evidence session. No write method is available."
    )
    parser.add_argument("--network-enabled", action="store_true", help="Allow only pinned Extended Sepolia public GET/WSS endpoints")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", help="Optional redacted JSON evidence path")
    args = parser.parse_args()

    evidence = run_p71_public_probe(network_enabled=args.network_enabled, timeout_seconds=args.timeout_seconds)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    summary_fields = (
        "status",
        "public_connectivity_valid",
        "public_rest_valid",
        "market_rules_fresh",
        "orderbook_fresh",
        "public_stream_valid",
        "public_stream_initial_snapshot_valid",
        "public_stream_sequence_valid",
        "public_stream_reconnect_count",
        "public_stream_heartbeat_evidence_mode",
        "public_rest_ws_consistency_valid",
        "private_account_read_evidence_valid",
        "private_account_stream_evidence_valid",
        "p71_complete",
        "block_reasons",
        "evidence_sha256",
    )
    print(json.dumps({key: evidence.get(key) for key in summary_fields}, ensure_ascii=True, sort_keys=True))
    return 0 if evidence.get("public_connectivity_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
