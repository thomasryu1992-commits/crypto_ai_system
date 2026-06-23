from __future__ import annotations

import compileall
import traceback

from config.settings import STEP150_VALIDATION_PATH
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso


def _run_step(name: str, fn):
    try:
        value = fn()
        return {"name": name, "status": "PASSED", "result": value if isinstance(value, dict) else str(value)}
    except SystemExit as exc:
        if exc.code in (0, None):
            return {"name": name, "status": "PASSED", "result": "SystemExit 0"}
        return {"name": name, "status": "FAILED", "error": f"SystemExit({exc.code})", "traceback": traceback.format_exc()}
    except Exception as exc:
        return {"name": name, "status": "FAILED", "error": repr(exc), "traceback": traceback.format_exc()}


def main() -> None:
    from run_full_cycle import run_full_cycle
    from check_scheduler_health import check_scheduler_health
    from data_health.health_check import run_data_health_check
    from bridge.research_trading_bridge import run_research_trading_bridge
    from execution.live_guard import run_live_readiness_check
    from analysis.live_shadow import run_live_shadow_report
    from integrations.spreadsheet_exporter import export_spreadsheet_schema_v3
    from reports.limited_live_readiness import build_limited_live_readiness_report
    from forward_test.paper_forward_runner import run_forward_test
    from run_step150_safety_tests import main as run_safety_tests

    steps = [
        ("compileall", lambda: {"ok": compileall.compile_dir(".", quiet=1)}),
        ("full_cycle", run_full_cycle),
        ("scheduler_health", check_scheduler_health),
        ("data_health_check", run_data_health_check),
        ("research_trading_bridge", run_research_trading_bridge),
        ("live_readiness_check", run_live_readiness_check),
        ("live_shadow_report", run_live_shadow_report),
        ("spreadsheet_schema_v3_export", export_spreadsheet_schema_v3),
        ("limited_live_readiness_report", build_limited_live_readiness_report),
        ("safety_tests", run_safety_tests),
        ("forward_test_2_iterations", lambda: run_forward_test(iterations=2)),
    ]

    results = [_run_step(name, fn) for name, fn in steps]
    passed = sum(1 for r in results if r["status"] == "PASSED")
    out = {
        "created_at": utc_now_iso(),
        "status": "PASSED" if passed == len(results) else "FAILED",
        "passed": passed,
        "total": len(results),
        "verified_scope": "Step131-150 spreadsheet-first guarded dry-run/paper/live-shadow/testnet-skeleton validation. No real exchange orders executed.",
        "results": results,
    }
    atomic_write_json(STEP150_VALIDATION_PATH, out)
    print(f"Step150 validation: {out['status']} {passed}/{len(results)}")
    if out["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
