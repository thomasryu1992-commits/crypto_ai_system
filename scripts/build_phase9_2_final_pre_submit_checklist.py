from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_final_pre_submit_checklist import (
    build_negative_fixture_results,
    persist_phase9_2_final_pre_submit_checklist,
)
from crypto_ai_system.config import load_config
from core.json_io import atomic_write_json


def main() -> int:
    report = persist_phase9_2_final_pre_submit_checklist()
    cfg = load_config()
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    atomic_write_json(latest / "phase9_2_final_pre_submit_checklist_negative_fixture_results.json", build_negative_fixture_results())
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "real_testnet_metadata_conditions_ready_for_submit_review_only": report["real_testnet_metadata_conditions_ready_for_submit_review_only"],
        "ready_for_separate_one_order_runtime_approval_review_only": report["ready_for_separate_one_order_runtime_approval_review_only"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
        "phase9_2_should_continue_count_estimate": report["phase9_2_should_continue_count_estimate"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
