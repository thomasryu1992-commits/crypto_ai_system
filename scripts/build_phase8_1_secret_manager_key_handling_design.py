from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase8_1_secret_manager_key_handling_design import (
    persist_phase8_1_secret_manager_key_handling_design_report,
)


def main() -> None:
    report = persist_phase8_1_secret_manager_key_handling_design_report()
    print(report.get("status"))
    print("phase8_1_secret_key_design_ready=", report.get("phase8_1_secret_key_design_ready"))
    print("secret_key_handling_design_guard_passed=", report.get("secret_key_handling_design_guard_passed"))
    print("phase8_2_write_path_dry_validation_may_begin=", report.get("phase8_2_write_path_dry_validation_may_begin"))
    print("secret_value_accessed=", report.get("secret_value_accessed"))
    print("secret_file_read=", report.get("secret_file_read"))
    print("secret_file_created=", report.get("secret_file_created"))
    print("actual_executor_enablement_performed=", report.get("actual_executor_enablement_performed"))
    print("actual_order_submission_performed=", report.get("actual_order_submission_performed"))
    print("ready_for_signed_testnet_execution=", report.get("ready_for_signed_testnet_execution"))
    print("testnet_order_submission_allowed=", report.get("testnet_order_submission_allowed"))
    print("place_order_enabled=", report.get("place_order_enabled"))
    print("cancel_order_enabled=", report.get("cancel_order_enabled"))
    print("signed_order_executor_enabled=", report.get("signed_order_executor_enabled"))
    print("block_reasons=", report.get("block_reasons"))


if __name__ == "__main__":
    main()
