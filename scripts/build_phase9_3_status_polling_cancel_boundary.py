from __future__ import annotations

import json
import sys
from pathlib import Path

from crypto_ai_system.validation.phase9_3_status_polling_cancel_boundary import persist_phase9_3_status_polling_cancel_boundary

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    report = persist_phase9_3_status_polling_cancel_boundary(ROOT, run_closure_first=True)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only": report.get("phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only"),
        "real_phase9_3_status_polling_may_begin": report.get("real_phase9_3_status_polling_may_begin"),
        "order_status_endpoint_called": report.get("order_status_endpoint_called"),
        "cancel_endpoint_called": report.get("cancel_endpoint_called"),
        "signature_created": report.get("signature_created"),
        "block_reasons": report.get("block_reasons", []),
    }, ensure_ascii=False, sort_keys=True))
