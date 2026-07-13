from __future__ import annotations
import argparse, json, sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))
from crypto_ai_system.execution.real_order_test_operator_run_package import read_json, validate_p68_operator_run_package

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True)
    p.add_argument("--p65-report", required=True)
    p.add_argument("--p66-report", required=True)
    p.add_argument("--p67-report", required=True)
    p.add_argument("--allow-fixture", action="store_true")
    args = p.parse_args()
    result = validate_p68_operator_run_package(read_json(args.package, {}), read_json(args.p65_report, {}), read_json(args.p66_report, {}), read_json(args.p67_report, {}), allow_fixture=args.allow_fixture)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["p68_operator_run_package_valid"] else 1
if __name__ == "__main__":
    raise SystemExit(main())
