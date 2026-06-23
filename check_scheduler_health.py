from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
SCHEDULER_LOG_DIR = STORAGE_DIR / "scheduler_logs"
REPORTS_DIR = STORAGE_DIR / "reports"


# ============================================================
# Console Safety
# ============================================================

def configure_utf8_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(value: Any = "") -> None:
    text = "" if value is None else str(value)

    try:
        print(text)
    except UnicodeEncodeError:
        try:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_text = text.encode(encoding, errors="backslashreplace").decode(
                encoding,
                errors="replace",
            )
            print(safe_text)
        except Exception:
            print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


configure_utf8_console()


# ============================================================
# Basic Helpers
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directories() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    SCHEDULER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {
            "status": "INVALID_JSON_TYPE",
            "error": "JSON root is not an object.",
            "path": str(path),
        }

    except Exception as exc:
        return {
            "status": "LOAD_FAILED",
            "error": str(exc),
            "path": str(path),
        }


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"

    return str(value).strip().upper()


def is_allowed_status(value: Any, allowed: List[str]) -> bool:
    status = normalize_status(value)
    allowed_set = {normalize_status(item) for item in allowed}
    return status in allowed_set


def first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return default


def safe_status(data: Dict[str, Any], default: str = "UNKNOWN") -> str:
    return str(
        first_non_empty(
            data.get("status"),
            data.get("overall_status"),
            data.get("result"),
            default=default,
        )
    )


def is_positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except Exception:
        return False


# ============================================================
# Daily Report Finder
# ============================================================

def daily_report_quality_score(data: Dict[str, Any]) -> int:
    if not isinstance(data, dict):
        return 0

    score = 0

    if data.get("report_date"):
        score += 1

    if data.get("current_price") is not None:
        score += 3

    if data.get("market_bias"):
        score += 3

    if data.get("research_score") is not None:
        score += 3

    summary = data.get("summary", {})
    if isinstance(summary, dict):
        if summary.get("base_case"):
            score += 2
        if summary.get("key_reason"):
            score += 2
        if summary.get("risk_note"):
            score += 2

    if data.get("status") in {"RESEARCH_CYCLE_COMPLETED", "COMPLETED"}:
        score += 1

    return score


def latest_daily_report_file() -> Optional[Path]:
    candidates: List[Path] = []

    candidates.extend(STORAGE_DIR.glob("daily_report_*.json"))
    candidates.extend(REPORTS_DIR.glob("daily_report_*.json"))

    candidates = [
        path
        for path in candidates
        if path.is_file()
        and "scheduler" not in path.name.lower()
        and "health" not in path.name.lower()
        and "result" not in path.name.lower()
    ]

    if not candidates:
        return None

    ranked = []

    for path in candidates:
        data = load_json_file(path)
        quality = daily_report_quality_score(data)
        modified_time = path.stat().st_mtime
        ranked.append((quality, modified_time, path))

    ranked = sorted(
        ranked,
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    return ranked[0][2]


def get_current_price(
    daily_report: Dict[str, Any],
    previous_scheduler_health: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    trading_cycle_result: Dict[str, Any],
    paper_report: Dict[str, Any],
    research_cycle_result: Dict[str, Any],
) -> Any:
    return first_non_empty(
        daily_report.get("current_price"),
        research_cycle_result.get("current_price"),
        previous_scheduler_health.get("current_price"),
        market_snapshot.get("current_price"),
        market_snapshot.get("price"),
        trading_cycle_result.get("current_price"),
        paper_report.get("current_price"),
        default=None,
    )


# ============================================================
# Operational Status
# ============================================================

def extract_operational_status(
    operational_dry_run_result: Dict[str, Any],
    operational_command_result: Dict[str, Any],
) -> str:
    """
    check_scheduler_health.py is the final judge.

    Some older run_operational_dry_run.py versions may still save status=FAILED
    because their internal allowed-status list is outdated.
    If the command itself ran successfully, scheduler-level checks decide final health.
    """
    if operational_command_result.get("ok") is True:
        return "PASSED"

    explicit_status = first_non_empty(
        operational_dry_run_result.get("status"),
        operational_dry_run_result.get("overall_status"),
        operational_dry_run_result.get("operational_dry_run"),
        default=None,
    )

    if explicit_status:
        return str(explicit_status)

    return "FAILED"


# ============================================================
# Command Runner
# ============================================================

def append_command_log(log_path: Path, command_result: Dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "",
        "=" * 80,
        f"[{command_result.get('name')}]",
        f"Started UTC: {command_result.get('started_at_utc')}",
        f"Finished UTC: {command_result.get('finished_at_utc')}",
        f"Status: {command_result.get('status')}",
        f"Return Code: {command_result.get('return_code')}",
        "",
        "[STDOUT TAIL]",
        str(command_result.get("stdout_tail", "")),
        "",
        "[STDERR TAIL]",
        str(command_result.get("stderr_tail", "")),
        "=" * 80,
        "",
    ]

    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_python_script(script_name: str, timeout_seconds: int = 180) -> Dict[str, Any]:
    script_path = PROJECT_ROOT / script_name
    log_path = SCHEDULER_LOG_DIR / "daily_operational_dry_run.log"

    started_at = now_utc()

    if not script_path.exists():
        result = {
            "name": f"COMMAND_{script_name}",
            "status": "COMMAND_NOT_FOUND",
            "script": str(script_path),
            "return_code": None,
            "ok": False,
            "stdout_tail": "",
            "stderr_tail": f"Script not found: {script_path}",
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
        }
        append_command_log(log_path, result)
        return result

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    command = [sys.executable, str(script_path)]

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
        )

        result = {
            "name": f"COMMAND_{script_name}",
            "status": "COMMAND_COMPLETED" if completed.returncode == 0 else "COMMAND_FAILED",
            "script": str(script_path),
            "command": command,
            "return_code": completed.returncode,
            "ok": completed.returncode == 0,
            "stdout_tail": completed.stdout[-4000:] if completed.stdout else "",
            "stderr_tail": completed.stderr[-4000:] if completed.stderr else "",
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
        }

        append_command_log(log_path, result)
        return result

    except subprocess.TimeoutExpired as exc:
        result = {
            "name": f"COMMAND_{script_name}",
            "status": "COMMAND_TIMEOUT",
            "script": str(script_path),
            "command": command,
            "return_code": None,
            "ok": False,
            "stdout_tail": str(exc.stdout)[-4000:] if exc.stdout else "",
            "stderr_tail": str(exc.stderr)[-4000:] if exc.stderr else "",
            "error": f"Timeout after {timeout_seconds} seconds.",
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
        }

        append_command_log(log_path, result)
        return result

    except Exception as exc:
        result = {
            "name": f"COMMAND_{script_name}",
            "status": "COMMAND_EXCEPTION",
            "script": str(script_path),
            "command": command,
            "return_code": None,
            "ok": False,
            "stdout_tail": "",
            "stderr_tail": traceback.format_exc()[-4000:],
            "error": str(exc),
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
        }

        append_command_log(log_path, result)
        return result


# ============================================================
# Health Check Helpers
# ============================================================

def build_check(
    name: str,
    passed: bool,
    severity: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity.upper(),
        "message": message,
        "details": details or {},
        "timestamp_utc": now_utc(),
    }


def add_check(
    checks: List[Dict[str, Any]],
    name: str,
    passed: bool,
    severity: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    checks.append(
        build_check(
            name=name,
            passed=passed,
            severity=severity,
            message=message,
            details=details,
        )
    )


def split_failures(checks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    error_failures = [
        check
        for check in checks
        if not check.get("passed") and check.get("severity") == "ERROR"
    ]

    warning_failures = [
        check
        for check in checks
        if not check.get("passed") and check.get("severity") == "WARNING"
    ]

    return {
        "error_failures": error_failures,
        "warning_failures": warning_failures,
    }


def calculate_health_status(checks: List[Dict[str, Any]]) -> str:
    failures = split_failures(checks)

    if failures["error_failures"]:
        return "UNHEALTHY"

    if failures["warning_failures"]:
        return "DEGRADED"

    return "HEALTHY"


# ============================================================
# Integrated Runners
# ============================================================

def run_markdown_report_writer() -> Dict[str, Any]:
    try:
        from core.report_writer import write_daily_markdown_report

        result = write_daily_markdown_report(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "DAILY_MARKDOWN_REPORT_WRITER",
            "status": "REPORT_WRITE_FAILED",
            "error": "Writer returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "DAILY_MARKDOWN_REPORT_WRITER",
            "status": "REPORT_WRITE_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def run_telegram_daily_report_builder() -> Dict[str, Any]:
    try:
        from notify.telegram_summary_builder import build_and_save_daily_telegram_message

        result = build_and_save_daily_telegram_message(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "TELEGRAM_SUMMARY_BUILDER",
            "status": "MESSAGE_BUILD_FAILED",
            "error": "Builder returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "TELEGRAM_SUMMARY_BUILDER",
            "status": "MESSAGE_BUILD_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def run_telegram_daily_report_sender() -> Dict[str, Any]:
    try:
        from notify.telegram_sender import send_daily_report_from_file

        result = send_daily_report_from_file(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "TELEGRAM_DAILY_REPORT_SENDER",
            "status": "SEND_FAILED",
            "error": "Sender returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "TELEGRAM_DAILY_REPORT_SENDER",
            "status": "SEND_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def run_performance_history_tracker() -> Dict[str, Any]:
    try:
        from core.performance_history_tracker import update_performance_history

        result = update_performance_history(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "PERFORMANCE_HISTORY_TRACKER",
            "status": "HISTORY_UPDATE_FAILED",
            "error": "Tracker returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "PERFORMANCE_HISTORY_TRACKER",
            "status": "HISTORY_UPDATE_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def run_signal_quality_evaluator() -> Dict[str, Any]:
    try:
        from core.signal_quality_evaluator import evaluate_signal_quality

        result = evaluate_signal_quality(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "SIGNAL_QUALITY_EVALUATOR",
            "status": "QUALITY_EVALUATION_FAILED",
            "error": "Evaluator returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "SIGNAL_QUALITY_EVALUATOR",
            "status": "QUALITY_EVALUATION_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def run_signal_calibration_advisor() -> Dict[str, Any]:
    try:
        from core.signal_calibration_advisor import create_signal_calibration_advice

        result = create_signal_calibration_advice(storage_dir=STORAGE_DIR)

        if isinstance(result, dict):
            return result

        return {
            "name": "SIGNAL_CALIBRATION_ADVISOR",
            "status": "CALIBRATION_ADVICE_FAILED",
            "error": "Advisor returned non-dict result.",
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "name": "SIGNAL_CALIBRATION_ADVISOR",
            "status": "CALIBRATION_ADVICE_FAILED",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


# ============================================================
# Files Map / Print
# ============================================================

def build_files_map() -> Dict[str, str]:
    latest_daily = latest_daily_report_file()

    return {
        "scheduler_health_result": str(STORAGE_DIR / "scheduler_health_result.json"),
        "scheduler_health_log": str(STORAGE_DIR / "scheduler_health_log.json"),
        "operational_dry_run_result": str(STORAGE_DIR / "operational_dry_run_result.json"),
        "runtime_guard_result": str(STORAGE_DIR / "runtime_guard_result.json"),
        "coinalyze_market_data": str(STORAGE_DIR / "coinalyze_market_data.json"),
        "market_snapshot": str(STORAGE_DIR / "market_snapshot.json"),
        "market_context": str(STORAGE_DIR / "market_context.json"),
        "research_cycle_result": str(STORAGE_DIR / "research_cycle_result.json"),
        "daily_report": str(latest_daily) if latest_daily else str(STORAGE_DIR / "daily_report_YYYY-MM-DD.json"),
        "dynamic_setup_result": str(STORAGE_DIR / "dynamic_setup_result.json"),
        "research_decision": str(STORAGE_DIR / "research_decision_result.json"),
        "trading_cycle_result": str(STORAGE_DIR / "trading_cycle_result.json"),
        "telegram_alert_result": str(STORAGE_DIR / "telegram_alert_result.json"),
        "spreadsheet_sync_result": str(STORAGE_DIR / "spreadsheet_sync_result.json"),
        "paper_performance_report": str(STORAGE_DIR / "paper_performance_report.json"),
        "daily_markdown_report_result": str(STORAGE_DIR / "daily_markdown_report_result.json"),
        "telegram_daily_report_message": str(STORAGE_DIR / "telegram_daily_report_message.json"),
        "telegram_daily_report_text": str(STORAGE_DIR / "telegram_daily_report_message.txt"),
        "telegram_daily_report_send_result": str(STORAGE_DIR / "telegram_daily_report_send_result.json"),
        "performance_history": str(STORAGE_DIR / "performance_history.jsonl"),
        "performance_history_summary": str(STORAGE_DIR / "performance_history_summary.json"),
        "performance_history_update_result": str(STORAGE_DIR / "performance_history_update_result.json"),
        "signal_quality_report": str(STORAGE_DIR / "signal_quality_report.json"),
        "signal_quality_report_text": str(STORAGE_DIR / "signal_quality_report.txt"),
        "signal_calibration_advice": str(STORAGE_DIR / "signal_calibration_advice.json"),
        "signal_calibration_advice_text": str(STORAGE_DIR / "signal_calibration_advice.txt"),
        "scheduler_log": str(SCHEDULER_LOG_DIR / "daily_operational_dry_run.log"),
        "windows_task_scheduler_log": str(SCHEDULER_LOG_DIR / "windows_task_scheduler.log"),
        "reports_dir": str(REPORTS_DIR),
    }


def print_health_summary(result: Dict[str, Any]) -> None:
    safe_print("=" * 80)
    safe_print("[SCHEDULER HEALTH CHECK]")
    safe_print("=" * 80)

    safe_print(f"Status: {result.get('status')}")
    safe_print(f"Operational Dry Run: {result.get('operational_dry_run')}")
    safe_print(f"Current Price: {result.get('current_price')}")
    safe_print(f"Dynamic Setup: {result.get('dynamic_setup')}")
    safe_print(f"Research Cycle: {result.get('research_cycle')}")
    safe_print(f"Research Decision Type: {result.get('research_decision_type')}")
    safe_print(f"Research Decision Source: {result.get('research_decision_source')}")
    safe_print(f"Has Conditional Setup: {result.get('has_conditional_setup')}")
    safe_print(f"Trading Cycle: {result.get('trading_cycle')}")
    safe_print(f"Trading Bot: {result.get('trading_bot')}")
    safe_print(f"Spreadsheet: {result.get('spreadsheet')}")
    safe_print(f"Telegram: {result.get('telegram')}")
    safe_print(f"Markdown Report: {result.get('markdown_report')}")
    safe_print(f"Telegram Daily Report: {result.get('telegram_daily_report')}")
    safe_print(f"Telegram Daily Send: {result.get('telegram_daily_send')}")
    safe_print(f"Performance History: {result.get('performance_history')}")
    safe_print(f"Signal Quality: {result.get('signal_quality')}")
    safe_print(f"Signal Calibration: {result.get('signal_calibration')}")
    safe_print(f"Total Checks: {result.get('total_checks')}")
    safe_print(f"Error Failures: {len(result.get('error_failures', []))}")
    safe_print(f"Warning Failures: {len(result.get('warning_failures', []))}")
    safe_print("")

    failed_checks = result.get("error_failures", []) + result.get("warning_failures", [])

    if failed_checks:
        safe_print("-" * 80)
        safe_print("[FAILED CHECKS]")

        for check in failed_checks:
            safe_print(
                f"- {check.get('severity')} / {check.get('name')}: {check.get('message')}"
            )

    safe_print("-" * 80)
    safe_print("[FILES]")

    files = result.get("files", {})
    for key, value in files.items():
        safe_print(f"{key}: {value}")

    safe_print("=" * 80)


# ============================================================
# Main
# ============================================================

def main() -> Dict[str, Any]:
    ensure_directories()

    checks: List[Dict[str, Any]] = []

    # --------------------------------------------------------
    # 1. Run operational dry run
    # --------------------------------------------------------

    operational_command_result = run_python_script(
        script_name="run_operational_dry_run.py",
        timeout_seconds=240,
    )

    # --------------------------------------------------------
    # 2. Load result files
    # --------------------------------------------------------

    operational_dry_run_result = load_json_file(STORAGE_DIR / "operational_dry_run_result.json")
    runtime_guard_result = load_json_file(STORAGE_DIR / "runtime_guard_result.json")
    market_snapshot = load_json_file(STORAGE_DIR / "market_snapshot.json")
    market_context = load_json_file(STORAGE_DIR / "market_context.json")
    research_cycle_result = load_json_file(STORAGE_DIR / "research_cycle_result.json")
    dynamic_setup_result = load_json_file(STORAGE_DIR / "dynamic_setup_result.json")
    research_decision_result = load_json_file(STORAGE_DIR / "research_decision_result.json")
    trading_cycle_result = load_json_file(STORAGE_DIR / "trading_cycle_result.json")
    telegram_alert_result = load_json_file(STORAGE_DIR / "telegram_alert_result.json")
    spreadsheet_sync_result = load_json_file(STORAGE_DIR / "spreadsheet_sync_result.json")
    paper_performance_report = load_json_file(STORAGE_DIR / "paper_performance_report.json")

    daily_report_path = latest_daily_report_file()
    daily_report = load_json_file(daily_report_path)

    previous_scheduler_health = load_json_file(STORAGE_DIR / "scheduler_health_result.json")

    # --------------------------------------------------------
    # 3. Extract core statuses
    # --------------------------------------------------------

    operational_dry_run_status = extract_operational_status(
        operational_dry_run_result=operational_dry_run_result,
        operational_command_result=operational_command_result,
    )

    current_price = get_current_price(
        daily_report=daily_report,
        previous_scheduler_health=previous_scheduler_health,
        market_snapshot=market_snapshot,
        trading_cycle_result=trading_cycle_result,
        paper_report=paper_performance_report,
        research_cycle_result=research_cycle_result,
    )

    dynamic_setup_status = safe_status(dynamic_setup_result)

    research_cycle_status = safe_status(
        research_cycle_result if research_cycle_result else daily_report
    )

    summary = daily_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    research_decision_type = str(
        first_non_empty(
            research_decision_result.get("decision_type"),
            research_decision_result.get("type"),
            research_decision_result.get("base_case"),
            dynamic_setup_result.get("research_decision_type"),
            dynamic_setup_result.get("decision_type"),
            summary.get("base_case"),
            default="UNKNOWN",
        )
    )

    research_decision_source = str(
        first_non_empty(
            research_decision_result.get("source"),
            dynamic_setup_result.get("source"),
            "dynamic_setup_generator",
            default="UNKNOWN",
        )
    )

    has_conditional_setup = bool(
        dynamic_setup_result.get("has_conditional_setup")
        or research_decision_result.get("has_conditional_setup")
        or "CONDITIONAL" in normalize_status(research_decision_type)
        or "WATCH" in normalize_status(research_decision_type)
    )

    trading_cycle_status = safe_status(trading_cycle_result)
    trading_bot_status = safe_status(paper_performance_report)
    spreadsheet_status = safe_status(spreadsheet_sync_result)
    telegram_status = safe_status(telegram_alert_result)

    # --------------------------------------------------------
    # 4. Base Health Checks
    # --------------------------------------------------------

    add_check(
        checks,
        "STORAGE_DIR_EXISTS",
        STORAGE_DIR.exists(),
        "ERROR",
        f"Storage directory exists: {STORAGE_DIR}",
    )

    add_check(
        checks,
        "SCHEDULER_LOG_DIR_EXISTS",
        SCHEDULER_LOG_DIR.exists(),
        "ERROR",
        f"Scheduler log directory exists: {SCHEDULER_LOG_DIR}",
    )

    add_check(
        checks,
        "REPORTS_DIR_EXISTS",
        REPORTS_DIR.exists(),
        "ERROR",
        f"Reports directory exists: {REPORTS_DIR}",
    )

    add_check(
        checks,
        "RUN_OPERATIONAL_DRY_RUN_SCRIPT_EXISTS",
        (PROJECT_ROOT / "run_operational_dry_run.py").exists(),
        "ERROR",
        "run_operational_dry_run.py must exist.",
    )

    add_check(
        checks,
        "COMMAND_OPERATIONAL_DRY_RUN_OK",
        operational_command_result.get("ok") is True,
        "ERROR",
        f"Operational dry run command return_code={operational_command_result.get('return_code')}.",
        operational_command_result,
    )

    add_check(
        checks,
        "OPERATIONAL_DRY_RUN_STATUS_ALLOWED",
        is_allowed_status(
            operational_dry_run_status,
            ["PASSED", "PASS", "SUCCESS", "OK", "COMPLETED"],
        ),
        "ERROR",
        f"Operational dry run status={operational_dry_run_status}.",
        {
            "status": operational_dry_run_status,
            "raw_status": operational_dry_run_result.get("status"),
        },
    )

    runtime_guard_status = safe_status(runtime_guard_result)
    runtime_guard_allowed = runtime_guard_result.get("allowed", True)

    add_check(
        checks,
        "RUNTIME_GUARD_ALLOWED",
        runtime_guard_allowed is not False and runtime_guard_status != "FAILED",
        "ERROR",
        f"Runtime guard status={runtime_guard_status}, allowed={runtime_guard_allowed}.",
        runtime_guard_result,
    )

    add_check(
        checks,
        "MARKET_SNAPSHOT_EXISTS",
        (STORAGE_DIR / "market_snapshot.json").exists(),
        "ERROR",
        "market_snapshot.json must exist.",
    )

    add_check(
        checks,
        "MARKET_CONTEXT_EXISTS",
        (STORAGE_DIR / "market_context.json").exists(),
        "WARNING",
        "market_context.json should exist.",
    )

    add_check(
        checks,
        "RESEARCH_CYCLE_RESULT_EXISTS",
        (STORAGE_DIR / "research_cycle_result.json").exists() or daily_report_path is not None,
        "ERROR",
        "research_cycle_result.json or daily_report_YYYY-MM-DD.json must exist.",
    )

    add_check(
        checks,
        "RESEARCH_CYCLE_STATUS_ALLOWED",
        is_allowed_status(
            research_cycle_status,
            ["RESEARCH_CYCLE_COMPLETED", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "ERROR",
        f"Research cycle status={research_cycle_status}.",
        {"status": research_cycle_status},
    )

    add_check(
        checks,
        "DAILY_REPORT_EXISTS",
        daily_report_path is not None and daily_report_path.exists(),
        "ERROR",
        "daily_report_YYYY-MM-DD.json must exist in storage/ or storage/reports/.",
        {"daily_report_path": str(daily_report_path) if daily_report_path else None},
    )

    add_check(
        checks,
        "CURRENT_PRICE_VALID",
        is_positive_number(current_price),
        "ERROR",
        f"Current price must be a positive number. current_price={current_price}.",
        {"current_price": current_price},
    )

    add_check(
        checks,
        "DYNAMIC_SETUP_STATUS_ALLOWED",
        is_allowed_status(
            dynamic_setup_status,
            ["DYNAMIC_SETUP_CREATED", "CREATED", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "WARNING",
        f"Dynamic setup status={dynamic_setup_status}.",
        {"status": dynamic_setup_status},
    )

    add_check(
        checks,
        "RESEARCH_DECISION_TYPE_EXISTS",
        normalize_status(research_decision_type) != "UNKNOWN",
        "WARNING",
        f"Research decision type={research_decision_type}.",
        {"research_decision_type": research_decision_type},
    )

    add_check(
        checks,
        "CONDITIONAL_SETUP_EXISTS",
        has_conditional_setup is True,
        "WARNING",
        f"Has conditional setup={has_conditional_setup}.",
        {"has_conditional_setup": has_conditional_setup},
    )

    add_check(
        checks,
        "TRADING_CYCLE_STATUS_ALLOWED",
        is_allowed_status(
            trading_cycle_status,
            ["CYCLE_COMPLETED", "TRADING_CYCLE_COMPLETED", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "ERROR",
        f"Trading cycle status={trading_cycle_status}.",
        {"status": trading_cycle_status},
    )

    add_check(
        checks,
        "TRADING_BOT_STATUS_ALLOWED",
        is_allowed_status(
            trading_bot_status,
            [
                "PAPER_WATCH_FINALIZED",
                "PAPER_TRADE_COMPLETED",
                "PAPER_PERFORMANCE_UPDATED",
                "WATCH",
                "UPDATED",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
            ],
        ),
        "ERROR",
        f"Trading bot status={trading_bot_status}.",
        {"status": trading_bot_status},
    )

    add_check(
        checks,
        "PAPER_MODE_CONFIRMED",
        normalize_status(paper_performance_report.get("mode", "paper")) == "PAPER",
        "ERROR",
        f"Trading mode should be paper. mode={paper_performance_report.get('mode', 'paper')}.",
        {"mode": paper_performance_report.get("mode", "paper")},
    )

    add_check(
        checks,
        "SPREADSHEET_STATUS_ALLOWED",
        is_allowed_status(
            spreadsheet_status,
            [
                "SYNC_COMPLETED",
                "SPREADSHEET_SYNC_COMPLETED",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
                "SKIPPED",
                "DISABLED",
            ],
        ),
        "WARNING",
        f"Spreadsheet status={spreadsheet_status}.",
        {"status": spreadsheet_status},
    )

    add_check(
        checks,
        "TELEGRAM_STATUS_ALLOWED",
        is_allowed_status(
            telegram_status,
            [
                "SENT",
                "TELEGRAM_SENT",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
                "SKIPPED",
                "DISABLED",
                "NOT_CONFIGURED",
                "SKIPPED_BY_DAILY_REPORT_MODE",
            ],
        ),
        "WARNING",
        f"Telegram status={telegram_status}.",
        {"status": telegram_status},
    )

    # --------------------------------------------------------
    # 5. Preliminary Result
    # --------------------------------------------------------

    preliminary_failures = split_failures(checks)

    preliminary_result = {
        "name": "SCHEDULER_HEALTH_CHECK",
        "status": calculate_health_status(checks),
        "operational_dry_run": operational_dry_run_status,
        "current_price": current_price,
        "dynamic_setup": dynamic_setup_status,
        "research_cycle": research_cycle_status,
        "research_decision_type": research_decision_type,
        "research_decision_source": research_decision_source,
        "has_conditional_setup": has_conditional_setup,
        "trading_cycle": trading_cycle_status,
        "trading_bot": trading_bot_status,
        "spreadsheet": spreadsheet_status,
        "telegram": telegram_status,
        "markdown_report": "NOT_RUN",
        "telegram_daily_report": "NOT_RUN",
        "telegram_daily_send": "NOT_RUN",
        "performance_history": "NOT_RUN",
        "signal_quality": "NOT_RUN",
        "signal_calibration": "NOT_RUN",
        "total_checks": len(checks),
        "error_failures": preliminary_failures["error_failures"],
        "warning_failures": preliminary_failures["warning_failures"],
        "checks": checks,
        "timezone": "Asia/Seoul",
        "daily_report_time": "19:00",
        "timestamp_utc": now_utc(),
        "files": build_files_map(),
    }

    write_json_file(STORAGE_DIR / "scheduler_health_result.json", preliminary_result)

    # --------------------------------------------------------
    # 6. Markdown Report
    # --------------------------------------------------------

    markdown_report_result = run_markdown_report_writer()
    markdown_status = safe_status(markdown_report_result)

    add_check(
        checks,
        "MARKDOWN_REPORT_WRITER_OK",
        is_allowed_status(
            markdown_status,
            ["REPORT_WRITTEN", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "ERROR",
        f"Markdown report writer status={markdown_status}.",
        markdown_report_result,
    )

    markdown_path = markdown_report_result.get("markdown_path")

    if markdown_path:
        markdown_file_path = Path(markdown_path)
        if not markdown_file_path.is_absolute():
            markdown_file_path = PROJECT_ROOT / markdown_file_path
        markdown_file_exists = markdown_file_path.exists()
    else:
        markdown_file_path = None
        markdown_file_exists = False

    add_check(
        checks,
        "MARKDOWN_REPORT_FILE_EXISTS",
        markdown_file_exists,
        "ERROR",
        f"Markdown report file must exist. path={markdown_path}.",
        {"markdown_path": str(markdown_file_path) if markdown_file_path else None},
    )

    # --------------------------------------------------------
    # 7. Telegram Daily Report Builder
    # --------------------------------------------------------

    telegram_daily_report_result = run_telegram_daily_report_builder()
    telegram_daily_report_status = safe_status(telegram_daily_report_result)

    add_check(
        checks,
        "TELEGRAM_DAILY_REPORT_BUILDER_OK",
        is_allowed_status(
            telegram_daily_report_status,
            ["MESSAGE_BUILT", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "ERROR",
        f"Telegram daily report builder status={telegram_daily_report_status}.",
        telegram_daily_report_result,
    )

    telegram_daily_report_text_path = STORAGE_DIR / "telegram_daily_report_message.txt"

    add_check(
        checks,
        "TELEGRAM_DAILY_REPORT_TEXT_EXISTS",
        telegram_daily_report_text_path.exists(),
        "ERROR",
        f"Telegram daily report text file must exist. path={telegram_daily_report_text_path}.",
        {"telegram_daily_report_text_path": str(telegram_daily_report_text_path)},
    )

    # --------------------------------------------------------
    # 8. Telegram Daily Report Sender
    # --------------------------------------------------------

    telegram_daily_send_result = run_telegram_daily_report_sender()
    telegram_daily_send_status = safe_status(telegram_daily_send_result)

    add_check(
        checks,
        "TELEGRAM_DAILY_REPORT_SEND_OK",
        is_allowed_status(
            telegram_daily_send_status,
            ["SENT", "DISABLED", "COMPLETED", "PASSED", "SUCCESS", "OK"],
        ),
        "WARNING",
        f"Telegram daily report sender status={telegram_daily_send_status}.",
        telegram_daily_send_result,
    )

    # --------------------------------------------------------
    # 9. Performance History Tracker
    # --------------------------------------------------------

    performance_history_result = run_performance_history_tracker()
    performance_history_status = safe_status(performance_history_result)

    add_check(
        checks,
        "PERFORMANCE_HISTORY_TRACKER_OK",
        is_allowed_status(
            performance_history_status,
            [
                "HISTORY_UPDATED",
                "SUMMARY_UPDATED",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
            ],
        ),
        "ERROR",
        f"Performance history tracker status={performance_history_status}.",
        performance_history_result,
    )

    # --------------------------------------------------------
    # 10. Signal Quality Evaluator
    # --------------------------------------------------------

    signal_quality_result = run_signal_quality_evaluator()
    signal_quality_status = safe_status(signal_quality_result)

    add_check(
        checks,
        "SIGNAL_QUALITY_EVALUATOR_OK",
        is_allowed_status(
            signal_quality_status,
            [
                "QUALITY_STRONG",
                "QUALITY_OK",
                "QUALITY_NEEDS_MORE_DATA",
                "QUALITY_WEAK",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
            ],
        ),
        "WARNING",
        f"Signal quality evaluator status={signal_quality_status}.",
        signal_quality_result,
    )

    # --------------------------------------------------------
    # 11. Signal Calibration Advisor
    # --------------------------------------------------------

    signal_calibration_result = run_signal_calibration_advisor()
    signal_calibration_status = safe_status(signal_calibration_result)

    add_check(
        checks,
        "SIGNAL_CALIBRATION_ADVISOR_OK",
        is_allowed_status(
            signal_calibration_status,
            [
                "CALIBRATION_ADVICE_CREATED",
                "COMPLETED",
                "PASSED",
                "SUCCESS",
                "OK",
            ],
        ),
        "WARNING",
        f"Signal calibration advisor status={signal_calibration_status}.",
        signal_calibration_result,
    )

    # --------------------------------------------------------
    # 12. Final Result
    # --------------------------------------------------------

    failures = split_failures(checks)
    final_status = calculate_health_status(checks)

    result = {
        "name": "SCHEDULER_HEALTH_CHECK",
        "status": final_status,
        "operational_dry_run": operational_dry_run_status,
        "current_price": current_price,
        "dynamic_setup": dynamic_setup_status,
        "research_cycle": research_cycle_status,
        "research_decision_type": research_decision_type,
        "research_decision_source": research_decision_source,
        "has_conditional_setup": has_conditional_setup,
        "trading_cycle": trading_cycle_status,
        "trading_bot": trading_bot_status,
        "spreadsheet": spreadsheet_status,
        "telegram": telegram_status,
        "markdown_report": markdown_status,
        "markdown_report_result": markdown_report_result,
        "telegram_daily_report": telegram_daily_report_status,
        "telegram_daily_report_result": telegram_daily_report_result,
        "telegram_daily_send": telegram_daily_send_status,
        "telegram_daily_send_result": telegram_daily_send_result,
        "performance_history": performance_history_status,
        "performance_history_result": performance_history_result,
        "signal_quality": signal_quality_status,
        "signal_quality_result": signal_quality_result,
        "signal_calibration": signal_calibration_status,
        "signal_calibration_result": signal_calibration_result,
        "total_checks": len(checks),
        "error_failures": failures["error_failures"],
        "warning_failures": failures["warning_failures"],
        "checks": checks,
        "timezone": "Asia/Seoul",
        "daily_report_time": "19:00",
        "timestamp_utc": now_utc(),
        "command_results": {
            "operational_dry_run": operational_command_result,
        },
        "files": build_files_map(),
    }

    write_json_file(STORAGE_DIR / "scheduler_health_result.json", result)
    write_json_file(STORAGE_DIR / "scheduler_health_log.json", result)

    print_health_summary(result)

    return result


if __name__ == "__main__":
    main()