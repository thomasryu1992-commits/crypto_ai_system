from __future__ import annotations

import json

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_one_order_execution_boundary import persist_p10_live_canary_one_order_execution_boundary


def main() -> int:
    cfg = load_config()
    report = persist_p10_live_canary_one_order_execution_boundary(cfg=cfg)
    print(json.dumps({
        "status": report.get("status"),
        "blocked": report.get("blocked"),
        "p10_live_canary_one_order_execution_boundary_id": report.get("p10_live_canary_one_order_execution_boundary_id"),
        "p10_live_canary_one_order_execution_boundary_ready": report.get("p10_live_canary_one_order_execution_boundary_ready"),
        "live_canary_execution_enabled": report.get("live_canary_execution_enabled"),
        "actual_live_order_submitted": report.get("actual_live_order_submitted"),
        "secret_value_accessed": report.get("secret_value_accessed"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
