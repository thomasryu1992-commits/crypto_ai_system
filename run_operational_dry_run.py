from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any

from config.settings import ensure_storage_dirs, storage_path
from core.console import configure_utf8_console, safe_print
from core.json_io import write_json, read_json
from core.runtime_guard import run_runtime_guard
from core.time_utils import utc_now_iso

configure_utf8_console()


COMMANDS = [
    ("REAL_MARKET_DATA_COLLECTOR", ["run_real_market_data_collector.py"]),
    ("MARKET_SNAPSHOT_BUILDER", ["build_market_snapshot.py"]),
    ("MARKET_CONTEXT_BUILDER", ["build_market_context.py"]),
    ("DYNAMIC_SETUP_GENERATOR", ["run_dynamic_setup.py"]),
    ("RESEARCH_CYCLE", ["run_research_cycle.py"]),
    ("RESEARCH_DECISION", ["run_research_decision.py"]),
    ("TRADING_CYCLE", ["run_trading_cycle.py"]),
]


def _run_command(name: str, args: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "name": name,
        "command": [sys.executable, *args],
        "return_code": proc.returncode,
        "ok": proc.returncode == 0,
        "started_at_utc": utc_now_iso(),
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-3000:],
    }


def _status_from_file(filename: str, key: str = "status") -> str:
    data = read_json(storage_path(filename), default={})
    return str(data.get(key, "UNKNOWN"))


def run_operational_dry_run() -> Dict[str, Any]:
    ensure_storage_dirs()
    log_lines = ["[OPERATIONAL DRY RUN]", f"Started: {utc_now_iso()}"]
    command_results = []

    for name, args in COMMANDS:
        result = _run_command(name, args)
        command_results.append(result)
        log_lines.append("=" * 80)
        log_lines.append(f"[{name}]")
        log_lines.append(f"return_code={result['return_code']}")
        log_lines.append(result.get("stdout_tail", ""))
        if result.get("stderr_tail"):
            log_lines.append("[STDERR]")
            log_lines.append(result["stderr_tail"])

    runtime_guard = run_runtime_guard()

    failed_checks = []
    for result in command_results:
        check_name = f"COMMAND_{result['name']}_OK"
        if not result.get("ok"):
            failed_checks.append({
                "name": check_name,
                "passed": False,
                "severity": "ERROR",
                "message": f"{result['name']} return_code={result.get('return_code')}",
                "details": result,
                "timestamp_utc": utc_now_iso(),
            })

    if not runtime_guard.get("allowed"):
        failed_checks.append({
            "name": "RUNTIME_GUARD_ALLOWED",
            "passed": False,
            "severity": "ERROR",
            "message": "Runtime guard blocked operational dry run.",
            "details": runtime_guard,
            "timestamp_utc": utc_now_iso(),
        })

    status = "PASSED" if not failed_checks else "FAILED"

    result = {
        "name": "OPERATIONAL_DRY_RUN",
        "status": status,
        "operational_dry_run_status": status,
        "return_code": 0 if status == "PASSED" else 1,
        "ok": status == "PASSED",
        "started_at_utc": log_lines[1].replace("Started: ", ""),
        "finished_at_utc": utc_now_iso(),
        "commands": command_results,
        "failed_checks": failed_checks,
        "error_failures": failed_checks,
        "warning_failures": [],
        "runtime_guard_result": runtime_guard,
        "summary": {
            "dynamic_setup": _status_from_file("dynamic_setup_result.json"),
            "research_decision_type": read_json(storage_path("research_decision_result.json"), default={}).get("decision_type", "UNKNOWN"),
            "research_decision_source": read_json(storage_path("research_decision_result.json"), default={}).get("source", "UNKNOWN"),
            "has_conditional_setup": read_json(storage_path("research_decision_result.json"), default={}).get("has_conditional_setup", False),
            "trading_cycle": _status_from_file("trading_cycle_result.json"),
            "trading_bot": read_json(storage_path("trading_cycle_result.json"), default={}).get("trading_bot_status", "UNKNOWN"),
            "spreadsheet": _status_from_file("spreadsheet_sync_result.json"),
            "telegram": _status_from_file("telegram_alert_result.json"),
            "current_price": read_json(storage_path("market_snapshot.json"), default={}).get("current_price"),
        },
    }

    write_json(storage_path("operational_dry_run_result.json"), result)
    log_path = storage_path("scheduler_logs/daily_operational_dry_run.log")
    Path(log_path).write_text("\n".join(log_lines), encoding="utf-8")
    return result


def main() -> Dict[str, Any]:
    result = run_operational_dry_run()
    safe_print("[OPERATIONAL DRY RUN]")
    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Error Failures: {len(result.get('error_failures', []))}")
    safe_print(f"Warning Failures: {len(result.get('warning_failures', []))}")
    safe_print(f"OPERATIONAL_DRY_RUN_STATUS={result.get('status')}")
    return result


if __name__ == "__main__":
    main()
