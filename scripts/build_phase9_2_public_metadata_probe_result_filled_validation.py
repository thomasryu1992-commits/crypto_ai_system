from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_public_metadata_probe_result_filled_validation import persist_phase9_2_public_metadata_probe_result_filled_validation


def main() -> int:
    report = persist_phase9_2_public_metadata_probe_result_filled_validation()
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "operator_filled_result_present": report["operator_filled_result_present"],
        "operator_filled_public_metadata_probe_result_validated": report["operator_filled_public_metadata_probe_result_validated"],
        "real_testnet_metadata_conditions_ready_for_submit_review_only": report["real_testnet_metadata_conditions_ready_for_submit_review_only"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
