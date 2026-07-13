from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from crypto_ai_system.execution.real_order_test_redacted_evidence_receipt import (
    atomic_write_json,
    validate_p67_receipt_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a redacted real /order/test evidence receipt without executing any endpoint.")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--p66-intake", required=True)
    parser.add_argument("--p66-validation-receipt", required=True)
    parser.add_argument("--output-dir", default="p67_validation_output")
    parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()
    validation, scan, bridge = validate_p67_receipt_files(
        args.receipt,
        args.p66_intake,
        args.p66_validation_receipt,
        allow_fixture=args.allow_fixture,
    )
    out = Path(args.output_dir)
    atomic_write_json(out / "p67_receipt_validation.json", validation)
    atomic_write_json(out / "p67_no_secret_scan.json", scan)
    atomic_write_json(out / "p67_order_test_dry_validation_bridge.json", bridge)
    print(json.dumps({"status": validation["status"], "valid": validation["p67_redacted_evidence_receipt_valid"]}, sort_keys=True))
    return 0 if validation["p67_redacted_evidence_receipt_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
