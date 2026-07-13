from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
for _path in (_PROJECT_ROOT, _SRC_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from crypto_ai_system.execution.canary_outcome_report import (  # noqa: E402
    run_canary_outcome_report_latest,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    report = run_canary_outcome_report_latest(root)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "canary_outcome_report_id": report.get("canary_outcome_report_id"),
                "live_scaled_readiness_recommendation": report.get(
                    "live_scaled_readiness_recommendation"
                ),
                "live_scaled_promotion_allowed": report.get("live_scaled_promotion_allowed"),
                "live_trading_enabled": report.get("live_trading_enabled"),
                "live_order_submission_allowed": report.get("live_order_submission_allowed"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.get("live_scaled_promotion_allowed") is False else 1


if __name__ == "__main__":
    raise SystemExit(main())
