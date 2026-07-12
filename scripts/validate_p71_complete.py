from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.execution.extended_read_only_connectivity import build_p71_complete_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and merge P71 public and external private read-only evidence")
    parser.add_argument("--public-evidence", required=True)
    parser.add_argument("--private-receipt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    public = json.loads(Path(args.public_evidence).read_text(encoding="utf-8"))
    private = json.loads(Path(args.private_receipt).read_text(encoding="utf-8"))
    result = build_p71_complete_evidence(public_evidence=public, private_receipt=private)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "p71_complete": result["p71_complete"], "block_reasons": result["block_reasons"], "evidence_sha256": result["evidence_sha256"]}, ensure_ascii=True, sort_keys=True))
    return 0 if result["p71_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
