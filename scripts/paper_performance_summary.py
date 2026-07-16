"""Print accumulated paper performance from the outcome feedback registry.

    py scripts/paper_performance_summary.py
    py scripts/paper_performance_summary.py --json

Reads the same performance report the feedback stage produces (expectancy,
win/loss, average R, drawdown, sample size, live-candidate eligibility).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except Exception:
    pass

from crypto_ai_system.feedback.performance_report_generator import (  # noqa: E402
    run_performance_report_latest,
)

_FIELDS = (
    "status",
    "recommendation",
    "sample_size",
    "closed_count",
    "expectancy",
    "win_loss_ratio",
    "average_R",
    "max_drawdown",
    "average_slippage",
    "average_latency_ms",
    "rejection_rate",
    "live_candidate_eligible",
)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Paper performance summary.")
    parser.add_argument("--json", action="store_true", help="emit full report as JSON")
    args = parser.parse_args(argv)

    report = run_performance_report_latest()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("=== paper performance (accumulated) ===")
    for field in _FIELDS:
        if field in report:
            print(f"{field:24}: {report[field]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
