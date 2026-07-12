from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_mock_submit_evidence_flow import persist_phase9_2_mock_submit_evidence_flow


def main() -> int:
    report = persist_phase9_2_mock_submit_evidence_flow()
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "mock_flow_ready_for_review_only_evidence_intake": report["mock_flow_ready_for_review_only_evidence_intake"],
        "real_phase9_3_status_polling_may_begin": report["real_phase9_3_status_polling_may_begin"],
        "real_phase9_4_testnet_reconciliation_may_begin": report["real_phase9_4_testnet_reconciliation_may_begin"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
