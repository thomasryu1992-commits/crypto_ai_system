from __future__ import annotations

import json

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_read_only_canary_preparation import persist_p9_live_read_only_canary_preparation


def main() -> int:
    cfg = load_config()
    report = persist_p9_live_read_only_canary_preparation(cfg=cfg)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "p9_live_read_only_canary_preparation_id": report.get("p9_live_read_only_canary_preparation_id"),
        "live_canary_preparation_ready_for_manual_approval_packet": report.get("live_canary_preparation_ready_for_manual_approval_packet"),
        "live_canary_execution_enabled": report.get("live_canary_execution_enabled"),
        "actual_live_order_submitted": report.get("actual_live_order_submitted"),
        "secret_value_accessed": report.get("secret_value_accessed"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
