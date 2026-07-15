"""Metrics dashboard for the sustained-paper scheduler.

Reads the scheduler's per-cycle metrics log and the latest performance report
and prints a compact status board with health warnings.

    py scripts/dashboard.py            # print the board once
    py scripts/dashboard.py --json     # machine-readable
    py scripts/dashboard.py --watch 30 # refresh every 30s (Ctrl+C to stop)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

import config.settings as settings  # noqa: E402
from core.json_io import read_jsonl  # noqa: E402
from crypto_ai_system.feedback.performance_report_generator import (  # noqa: E402
    run_performance_report_latest,
)
from crypto_ai_system.scheduler.dashboard import build_dashboard  # noqa: E402


def _gather() -> dict:
    records = read_jsonl(settings.LATEST_DIR / "scheduler_metrics.jsonl")
    report = run_performance_report_latest()
    return build_dashboard(records, report)


def _render(board: dict) -> str:
    p = board["performance"]
    lines = [
        "=== scheduler dashboard ===",
        f"cycles         : {board['cycles']} "
        f"(ok {board['ok_cycles']} / err {board['error_cycles']}, rate {board['ok_rate']})",
        f"window         : {board['first_cycle_at']} -> {board['last_cycle_at']}",
        f"trades placed  : {board['trades_placed']}",
        f"synthetic cyc. : {board['synthetic_cycles']}",
        "--- performance (accumulated) ---",
        f"status         : {p['status']}",
        f"closed / sample: {p['closed_count']} / {p['sample_size']}",
        f"expectancy     : {p['expectancy']}",
        f"win/loss ratio : {p['win_loss_ratio']}",
        f"average R      : {p['average_R']}",
        f"max drawdown   : {p['max_drawdown']}",
        f"live eligible  : {p['live_candidate_eligible']}",
    ]
    warnings = board["warnings"]
    if warnings:
        lines.append("--- warnings ---")
        lines.extend(f"  ! {w}" for w in warnings)
    else:
        lines.append("warnings       : none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Scheduler metrics dashboard.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--watch", type=float, default=None, help="refresh every N seconds")
    args = parser.parse_args(argv)

    def show() -> None:
        board = _gather()
        print(json.dumps(board, indent=2, default=str) if args.json else _render(board))

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")  # clear screen
                show()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0
    else:
        show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
