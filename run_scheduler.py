"""Run the trading pipeline on a schedule (sustained real-data paper).

    py run_scheduler.py                 # run forever, one cycle per hour
    py run_scheduler.py --interval 900  # every 15 minutes
    py run_scheduler.py --cycles 24     # 24 cycles then stop
    py run_scheduler.py --once          # a single cycle

Each cycle runs the five-agent pipeline and logs the stage statuses plus the
accumulated performance metrics (expectancy, closed trades, live-candidate
eligibility). No orders are placed unless the signed-testnet path is explicitly
enabled; by default this just accumulates paper outcomes on real data.

Runs in the foreground; Ctrl+C stops it cleanly. For an unattended setup, point
Windows Task Scheduler at `run_pipeline.py` on an interval instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parent
    for p in (str(root / "src"), str(root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=True)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    import config.settings as settings
    from core.json_io import append_jsonl, atomic_write_json
    from core.run_lock import PipelineAlreadyRunning, pipeline_run_lock
    from core.time_utils import utc_now_iso
    from crypto_ai_system.pipeline import Pipeline
    from crypto_ai_system.pipeline.exit_codes import EXIT_ALREADY_RUNNING, exit_code_for, is_healthy
    from crypto_ai_system.scheduler.loop import run_scheduler_loop

    parser = argparse.ArgumentParser(description="Run the pipeline on a schedule.")
    parser.add_argument("--interval", type=float, default=3600.0, help="seconds between cycles")
    parser.add_argument("--cycles", type=int, default=None, help="number of cycles (default: forever)")
    parser.add_argument("--once", action="store_true", help="run exactly one cycle")
    args = parser.parse_args(argv)

    cycles = 1 if args.once else args.cycles
    heartbeat_path = settings.LATEST_DIR / "scheduler_heartbeat.json"
    metrics_log = settings.LATEST_DIR / "scheduler_metrics.jsonl"

    def run_cycle() -> dict:
        try:
            with pipeline_run_lock():
                run = Pipeline().run_once()
        except PipelineAlreadyRunning as exc:
            # An overlapping manual run holds storage/latest — skip this cycle
            # rather than interleave two runs' artifacts.
            return {
                "cycle_id": None,
                "stages": {},
                "trade_executed": False,
                "halted": False,
                "exit_code": EXIT_ALREADY_RUNNING,
                "halt_reason": str(exc),
                "healthy": False,
                "data_is_synthetic": None,
                "metrics": {},
            }
        code, halt_reason = exit_code_for(run)
        stages = {r.stage: r.status.value for r in run.results}
        data = run.by_stage("data")
        feedback = run.by_stage("feedback")
        report = (feedback.outputs.get("performance_report") if feedback else {}) or {}
        metrics = {
            "closed_count": report.get("closed_count"),
            "expectancy": report.get("expectancy"),
            "win_loss_ratio": report.get("win_loss_ratio"),
            "max_drawdown": report.get("max_drawdown"),
            "live_candidate_eligible": report.get("live_candidate_eligible"),
        }
        return {
            "cycle_id": run.cycle_id,
            "stages": stages,
            "trade_executed": run.trade_executed,
            "halted": run.halted,
            "exit_code": code,
            "halt_reason": halt_reason,
            "healthy": is_healthy(code),
            "data_is_synthetic": bool(data.outputs.get("data_is_synthetic")) if data else None,
            "metrics": metrics,
        }

    def on_result(record: dict) -> None:
        ts = utc_now_iso()
        r = record.get("result") or {}
        # Compact per-cycle metrics row for the dashboard.
        row = {
            "ts": ts,
            "cycle": record["cycle"],
            "cycle_id": r.get("cycle_id"),
            "ok": record["ok"],
            "duration_s": record.get("duration_s"),
            "stages": r.get("stages"),
            "trade_executed": r.get("trade_executed"),
            "halted": r.get("halted"),
            "exit_code": r.get("exit_code"),
            "halt_reason": r.get("halt_reason"),
            "healthy": r.get("healthy", record["ok"] is not False),
            "data_is_synthetic": r.get("data_is_synthetic"),
            **(r.get("metrics") or {}),
        }
        append_jsonl(metrics_log, row)

        if record["ok"]:
            stage_str = " ".join(f"{k}={v}" for k, v in (r.get("stages") or {}).items())
            m = r.get("metrics") or {}
            halt = f" HALT({r.get('halt_reason')})" if not r.get("healthy", True) else ""
            print(f"[{ts}] cycle {record['cycle']} ({record['duration_s']}s) exit={r.get('exit_code')}{halt} "
                  f"{stage_str} trade={r.get('trade_executed')} | "
                  f"closed={m.get('closed_count')} exp={m.get('expectancy')} "
                  f"elig={m.get('live_candidate_eligible')}")
        else:
            print(f"[{ts}] cycle {record['cycle']} FAILED: {record['error']}")
        atomic_write_json(heartbeat_path, {"last_cycle_at": ts, **record})

    print(f"scheduler starting: interval={args.interval}s cycles={cycles or 'forever'}")
    try:
        records = run_scheduler_loop(
            run_cycle, cycles=cycles, interval=args.interval, on_result=on_result
        )
    except KeyboardInterrupt:
        print("\nscheduler stopped by user")
        return 0

    # A cycle is unhealthy if the loop caught an exception OR the pipeline
    # halted (fatal block / error). Task Scheduler sees a non-zero result then.
    def _healthy(rec: dict) -> bool:
        return bool(rec.get("ok")) and (rec.get("result") or {}).get("healthy", True)

    healthy = sum(1 for r in records if _healthy(r))
    print(f"done: {healthy}/{len(records)} cycles healthy")
    print(json.dumps({"cycles": len(records), "healthy": healthy}, indent=2))
    return 0 if healthy == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
