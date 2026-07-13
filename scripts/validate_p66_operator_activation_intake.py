from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from crypto_ai_system.execution.operator_activation_intake_for_real_order_test import validate_p66_intake_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one operator-supplied P66 activation intake without executing /order/test.")
    parser.add_argument("--intake", required=True)
    parser.add_argument("--p65-report", default="storage/latest/p65_operator_installed_testnet_sender_executable_report.json")
    parser.add_argument("--nonce-registry", default="storage/registries/p66_operator_activation_intake_for_real_order_test_registry.jsonl")
    parser.add_argument("--output")
    args = parser.parse_args()

    registry_path = Path(args.nonce_registry)
    rows = []
    if registry_path.exists():
        for line in registry_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    seen = {str(row.get("one_shot_nonce_sha256")) for row in rows if row.get("one_shot_nonce_sha256")}
    validation, receipt = validate_p66_intake_file(
        args.intake,
        args.p65_report,
        seen_nonce_hashes=seen,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validation": validation, "receipt": receipt}, ensure_ascii=False, sort_keys=True))
    return 0 if validation["p66_operator_activation_intake_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
