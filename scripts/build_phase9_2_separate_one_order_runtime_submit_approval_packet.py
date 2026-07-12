from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_separate_one_order_runtime_submit_approval_packet import (
    build_negative_fixture_results,
    persist_phase9_2_separate_one_order_runtime_submit_approval_packet,
)


def main() -> int:
    report = persist_phase9_2_separate_one_order_runtime_submit_approval_packet()
    cfg = load_config()
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    atomic_write_json(latest / "phase9_2_separate_one_order_runtime_submit_approval_packet_negative_fixture_results.json", build_negative_fixture_results())
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "operator_filled_approval_present": report["operator_filled_approval_present"],
        "operator_filled_approval_validated": report["operator_filled_approval_validated"],
        "ready_for_one_order_runtime_submit_operator_review_only": report["ready_for_one_order_runtime_submit_operator_review_only"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
