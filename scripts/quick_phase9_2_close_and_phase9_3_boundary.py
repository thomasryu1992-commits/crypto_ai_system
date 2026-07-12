from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.validation.phase9_2_closure_packet import persist_phase9_2_closure_packet
from crypto_ai_system.validation.phase9_3_status_polling_cancel_boundary import persist_phase9_3_status_polling_cancel_boundary


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _quick_ready(payload: dict) -> bool:
    return bool(
        payload.get("blocked") is False
        and payload.get("fail_closed") is False
        and payload.get("operator_filled_approval_validated") is True
        and payload.get("ready_for_one_order_runtime_submit_operator_review_only") is True
        and payload.get("public_metadata_conditions_ready_for_submit_review_only") is True
        and payload.get("real_testnet_submit_may_begin") is False
    )


def _run_script(rel: str) -> dict:
    proc = subprocess.run([sys.executable, str(ROOT / rel)], cwd=ROOT, text=True, capture_output=True, timeout=120)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except Exception:
        payload = {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
    return {"script": rel, "returncode": proc.returncode, "payload": payload, "stderr": proc.stderr[-800:]}


if __name__ == "__main__":
    actions = []
    quick_report_path = ROOT / "storage" / "latest" / "phase9_2_quick_one_order_approval_ready_check_report.json"
    existing_quick = _read_json(quick_report_path)
    if _quick_ready(existing_quick):
        actions.append({
            "script": "scripts/quick_phase9_2_one_order_approval_ready_check.py",
            "skipped": True,
            "reason": "existing_quick_ready_check_report_already_valid",
            "payload": existing_quick,
        })
    else:
        quick_script = ROOT / "scripts" / "quick_phase9_2_one_order_approval_ready_check.py"
        if quick_script.exists():
            actions.append(_run_script("scripts/quick_phase9_2_one_order_approval_ready_check.py"))

    closure = persist_phase9_2_closure_packet(ROOT)
    boundary = persist_phase9_3_status_polling_cancel_boundary(ROOT, run_closure_first=False)
    out = {
        "actions": actions,
        "closure_status": closure.get("status"),
        "phase9_2_closed_review_only": closure.get("phase9_2_closed_review_only"),
        "ready_for_phase9_3_boundary_review_only": closure.get("ready_for_phase9_3_boundary_review_only"),
        "phase9_3_boundary_status": boundary.get("status"),
        "phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only": boundary.get("phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only"),
        "real_testnet_submit_may_begin": False,
        "real_phase9_3_status_polling_may_begin": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "signature_created": False,
        "signed_request_created": False,
    }
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
