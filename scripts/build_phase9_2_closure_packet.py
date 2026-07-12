from __future__ import annotations

import json
import sys
from pathlib import Path

from crypto_ai_system.validation.phase9_2_closure_packet import persist_phase9_2_closure_packet

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    report = persist_phase9_2_closure_packet(ROOT)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "phase9_2_closed_review_only": report.get("phase9_2_closed_review_only"),
        "ready_for_phase9_3_boundary_review_only": report.get("ready_for_phase9_3_boundary_review_only"),
        "real_testnet_submit_may_begin": report.get("real_testnet_submit_may_begin"),
        "block_reasons": report.get("block_reasons", []),
    }, ensure_ascii=False, sort_keys=True))
