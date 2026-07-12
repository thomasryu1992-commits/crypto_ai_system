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

from crypto_ai_system.validation.phase9_2_public_metadata_probe_bridge import persist_phase9_2_public_metadata_probe_bridge


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 9.2 public metadata probe bridge / no order submit")
    parser.add_argument(
        "--execute-public-metadata-probe",
        action="store_true",
        help="Call public testnet metadata endpoints only and bridge a valid redacted result to filled validation. Never calls order/private endpoints.",
    )
    args = parser.parse_args()
    report = persist_phase9_2_public_metadata_probe_bridge(execute_network=args.execute_public_metadata_probe)
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "network_execution_requested": report["network_execution_requested"],
        "operator_filled_result_payload_created": report["operator_filled_result_payload_created"],
        "operator_filled_public_metadata_probe_result_validated": report["operator_filled_public_metadata_probe_result_validated"],
        "real_testnet_metadata_conditions_ready_for_submit_review_only": report["real_testnet_metadata_conditions_ready_for_submit_review_only"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
