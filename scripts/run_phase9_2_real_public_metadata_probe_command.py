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

from crypto_ai_system.validation.phase9_2_real_public_metadata_probe_command import persist_phase9_2_real_public_metadata_probe_command


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 9.2 real public metadata probe command / no order submit")
    parser.add_argument(
        "--execute-public-metadata-probe",
        action="store_true",
        help="Call public testnet metadata endpoints only. Never calls order/private endpoints.",
    )
    args = parser.parse_args()
    report = persist_phase9_2_real_public_metadata_probe_command(execute_network=args.execute_public_metadata_probe)
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "network_execution_requested": report["network_execution_requested"],
        "public_metadata_network_probe_command_ready": report["public_metadata_network_probe_command_ready"],
        "public_metadata_network_probe_performed": report["public_metadata_network_probe_performed"],
        "public_metadata_network_probe_result_validated": report["public_metadata_network_probe_result_validated"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
