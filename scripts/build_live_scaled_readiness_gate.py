from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
for _path in (_PROJECT_ROOT, _SRC_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from crypto_ai_system.execution.live_scaled_readiness_gate import (  # noqa: E402
    run_live_scaled_readiness_gate_latest,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    gate = run_live_scaled_readiness_gate_latest(root)
    print(
        json.dumps(
            {
                "status": gate.get("status"),
                "gate_decision": gate.get("gate_decision"),
                "blocked_reasons": gate.get("blocked_reasons", []),
                "live_scaled_execution_enabled_by_this_module": gate.get(
                    "live_scaled_execution_enabled_by_this_module"
                ),
                "live_trading_allowed_by_this_module": gate.get(
                    "live_trading_allowed_by_this_module"
                ),
                "live_order_submission_allowed": gate.get("live_order_submission_allowed"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if str(gate.get("gate_decision") or "").lower().startswith("block") else 1


if __name__ == "__main__":
    raise SystemExit(main())
