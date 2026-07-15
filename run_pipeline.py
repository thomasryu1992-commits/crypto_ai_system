"""Lean entry point for the five-agent trading loop.

Replaces run_full_cycle.py's ~250 lines of governance ceremony with the
real pipeline: data -> research -> validation -> trading -> feedback.

Usage:
    python run_pipeline.py            # run one cycle, print the stage report
    python run_pipeline.py --json     # emit the run as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parent
    src = root / "src"
    for path in (str(src), str(root)):
        if path not in sys.path:
            sys.path.insert(0, path)
    # Load .env before any config module is imported (config reads env at
    # import time). Safe no-op if python-dotenv or the file is absent.
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    from crypto_ai_system.pipeline import Pipeline, StageStatus

    parser = argparse.ArgumentParser(description="Run one lean trading cycle.")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args(argv)

    run = Pipeline().run_once()

    if args.json:
        payload = {
            "trade_executed": run.trade_executed,
            "halted": run.halted,
            "stages": [
                {
                    "stage": r.stage,
                    "status": r.status.value,
                    "reasons": r.reasons,
                    "duration_ms": r.duration_ms,
                }
                for r in run.results
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("=== trading cycle ===")
        print(run.report())
        print("=====================")
        print(f"trade_executed={run.trade_executed} halted={run.halted}")

    # Exit non-zero if the pipeline halted on error/fatal block.
    any_error = any(r.status is StageStatus.ERROR for r in run.results)
    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
