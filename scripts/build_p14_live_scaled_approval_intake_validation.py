from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_scaled_approval_intake_validation import persist_live_scaled_approval_intake_validation


def main() -> int:
    cfg = load_config(Path.cwd())
    report = persist_live_scaled_approval_intake_validation(cfg=cfg)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "waiting": report.get("waiting"),
        "live_scaled_approval_valid_review_only": report.get("live_scaled_approval_valid_review_only"),
        "limited_live_scaled_auto_trading_allowed": report.get("limited_live_scaled_auto_trading_allowed"),
        "live_scaled_execution_enabled": report.get("live_scaled_execution_enabled"),
        "live_order_submission_allowed": report.get("live_order_submission_allowed"),
        "secret_value_accessed": report.get("secret_value_accessed"),
        "report_path": "storage/latest/p14_live_scaled_approval_intake_validation_report.json",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
