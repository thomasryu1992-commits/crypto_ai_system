from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_scaled_readiness_review import persist_live_scaled_readiness_review


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_live_scaled_readiness_review(cfg=cfg)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "waiting": report.get("waiting"),
        "ready_for_separate_live_scaled_approval_review_only": report.get("ready_for_separate_live_scaled_approval_review_only"),
        "live_scaled_execution_enabled": report.get("live_scaled_execution_enabled"),
        "live_order_submission_allowed": report.get("live_order_submission_allowed"),
        "secret_value_accessed": report.get("secret_value_accessed"),
        "report_path": "storage/latest/p13_live_scaled_readiness_review_report.json",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
