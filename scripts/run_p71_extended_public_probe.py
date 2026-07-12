from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.execution.extended_read_only_connectivity import run_p71_public_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P71 Extended testnet public read-only REST/WebSocket probe. No write method is available.")
    parser.add_argument("--network-enabled", action="store_true", help="Allow only the hard-coded Extended Sepolia public GET/WSS endpoints")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", help="Optional redacted JSON evidence path")
    args = parser.parse_args()
    evidence = run_p71_public_probe(network_enabled=args.network_enabled, timeout_seconds=args.timeout_seconds)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: evidence.get(k) for k in ("status", "public_connectivity_valid", "private_account_read_evidence_valid", "p71_complete", "block_reasons", "evidence_sha256")}, ensure_ascii=True, sort_keys=True))
    return 0 if evidence.get("public_connectivity_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
