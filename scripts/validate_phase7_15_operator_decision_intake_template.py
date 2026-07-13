from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.config import load_config
from core.json_io import read_json
from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    persist_phase7_15_operator_decision_intake_template_report,
)


def main() -> None:
    report = persist_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)
    cfg = load_config()
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    validation = read_json(latest / "phase7_15_operator_decision_intake_template_validation_report.json", default={})
    fixture_results = read_json(latest / "phase7_15_negative_fixture_results.json", default={})
    package_scan = read_json(latest / "phase7_15_package_boundary_scan.json", default={})
    print(report.get("status"))
    print("phase7_15_template_validation_passed=", validation.get("passed_review_only"))
    print("all_negative_fixtures_blocked=", fixture_results.get("all_negative_fixtures_blocked"))
    print("package_boundary_passed=", package_scan.get("blocked") is False)
    print("approval_intake_validator_reused=", validation.get("approval_intake_validator_reused"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))


if __name__ == "__main__":
    main()
