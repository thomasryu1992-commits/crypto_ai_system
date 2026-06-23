from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config.settings import KNOWLEDGE_BASE_DIR, LINT_DIR, PROJECT_ROOT, STORAGE_DIR
from scripts.json_utils import append_json_log, load_json, save_json
from reset_paper_state import RESET_FILES

RESULT_PATH = STORAGE_DIR / "full_regression_test_result.json"
LOG_PATH = STORAGE_DIR / "full_regression_test_log.json"
MARKET_CONTEXT_PATH = STORAGE_DIR / "market_context.json"


def main() -> None:
    started = now()
    checks: List[Dict[str, Any]] = []
    commands: Dict[str, Any] = {}

    print("=" * 80)
    print("[STEP 50] FULL REGRESSION TEST")
    print("=" * 80)

    try:
        disabled_env = test_env(bridge=False)
        enabled_env = test_env(bridge=True)

        print("[1/8] initial reset")
        commands["reset_1"] = run_reset()
        check(checks, "RESET_1_OK", commands["reset_1"]["ok"], "Initial reset should succeed.", commands["reset_1"])

        print("[2/8] research cycle")
        commands["research_cycle"] = run_script("run_research_cycle.py", disabled_env)
        check(checks, "RESEARCH_CYCLE_OK", commands["research_cycle"]["ok"], "Research cycle should succeed.", commands["research_cycle"])
        validate_kb(checks)
        validate_research_decision(checks)

        print("[3/8] disabled reset")
        commands["reset_disabled"] = run_reset()
        check(checks, "RESET_DISABLED_OK", commands["reset_disabled"]["ok"], "Disabled test reset should succeed.", commands["reset_disabled"])
        write_market_context(106850)
        print("[4/8] disabled trading cycle")
        commands["cycle_disabled"] = run_script("run_trading_cycle.py", disabled_env)
        disabled_cycle = load_json(STORAGE_DIR / "trading_cycle_result.json", {})
        check(checks, "BRIDGE_DISABLED_CYCLE_OK", commands["cycle_disabled"]["ok"], "Trading cycle should succeed with bridge disabled.", commands["cycle_disabled"])
        check(checks, "BRIDGE_DISABLED_SKIPPED", bridge_status(disabled_cycle) == "SKIPPED", "Bridge should be SKIPPED when disabled.", disabled_cycle)
        check(checks, "BRIDGE_DISABLED_NO_EXECUTION", reconciliation_status() in {"NO_EXECUTION_FOUND", None}, "No execution should exist when bridge is disabled.", load_json(STORAGE_DIR / "execution_reconciliation_result.json", {}))

        print("[5/8] enabled reset")
        commands["reset_enabled"] = run_reset()
        check(checks, "RESET_ENABLED_OK", commands["reset_enabled"]["ok"], "Enabled test reset should succeed.", commands["reset_enabled"])

        write_market_context(106850)
        print("[6/8] watch cycle")
        commands["cycle_watch"] = run_script("run_trading_cycle.py", enabled_env)
        watch_cycle = load_json(STORAGE_DIR / "trading_cycle_result.json", {})
        watch_summary = watch_cycle.get("trading_summary", {}) if isinstance(watch_cycle.get("trading_summary"), dict) else {}
        check(checks, "WATCH_CYCLE_OK", commands["cycle_watch"]["ok"], "Watch cycle should succeed.", commands["cycle_watch"])
        check(checks, "PAPER_WATCH_CREATED", watch_summary.get("trading_bot_status") == "PAPER_WATCH_CREATED", "Expected PAPER_WATCH_CREATED.", watch_summary)
        check(checks, "WATCH_ACTIVE_COUNT_1", count(watch_summary, "paper_watch_summary", "active_watch_count") == 1, "Active watch count should be 1.", watch_summary)
        check(checks, "WATCH_OPEN_POSITION_COUNT_0", count(watch_summary, "paper_position_summary", "open_position_count") == 0, "Open position count should be 0.", watch_summary)

        write_market_context(107600)
        print("[7/8] position cycle")
        commands["cycle_position"] = run_script("run_trading_cycle.py", enabled_env)
        position_cycle = load_json(STORAGE_DIR / "trading_cycle_result.json", {})
        position_summary = position_cycle.get("trading_summary", {}) if isinstance(position_cycle.get("trading_summary"), dict) else {}
        risk = load_json(STORAGE_DIR / "risk_check_result.json", {})
        order_execution = load_json(STORAGE_DIR / "order_execution_result.json", {})
        router = load_json(STORAGE_DIR / "exchange_router_result.json", {})
        mock = load_json(STORAGE_DIR / "mock_order_result.json", {})
        reconciliation = load_json(STORAGE_DIR / "execution_reconciliation_result.json", {})

        check(checks, "POSITION_CYCLE_OK", commands["cycle_position"]["ok"], "Position cycle should succeed.", commands["cycle_position"])
        check(checks, "PAPER_POSITION_OPENED", position_summary.get("trading_bot_status") == "PAPER_POSITION_OPENED", "Expected PAPER_POSITION_OPENED.", position_summary)
        check(checks, "POSITION_OPEN_COUNT_1", count(position_summary, "paper_position_summary", "open_position_count") == 1, "Open position count should be 1.", position_summary)
        check(checks, "BRIDGE_MOCK_ORDER_ACCEPTED", bridge_status(position_cycle) == "MOCK_ORDER_ACCEPTED", "Bridge should accept mock order.", position_summary)
        check(checks, "RISK_APPROVED", risk.get("status") == "APPROVED" and risk.get("approved") is True, "Risk Manager should approve mock order.", risk)
        check(checks, "ORDER_EXECUTION_ACCEPTED", order_execution.get("status") == "MOCK_ORDER_ACCEPTED", "Order Executor should return MOCK_ORDER_ACCEPTED.", order_execution)
        check(checks, "ROUTED_TO_MOCK", router.get("status") == "ROUTED_TO_MOCK", "Exchange Router should route to mock.", router)
        check(checks, "MOCK_ACCEPTED", mock.get("status") == "ACCEPTED", "Mock Exchange should accept order.", mock)
        check(checks, "LIVE_ORDER_FALSE", live_order_executed(order_execution, router, mock) is False, "No live order should be executed.", {"order_execution": order_execution, "router": router, "mock": mock})
        check(checks, "RECONCILED", reconciliation.get("status") == "RECONCILED" and reconciliation.get("reconciled") is True, "Execution reconciliation should be RECONCILED.", reconciliation)
        validate_reconciliation_checks(checks, reconciliation)

        map_before = load_json(STORAGE_DIR / "paper_order_execution_map.json", {})
        print("[8/8] duplicate cycle")
        commands["cycle_duplicate"] = run_script("run_trading_cycle.py", enabled_env)
        map_after = load_json(STORAGE_DIR / "paper_order_execution_map.json", {})
        check(checks, "DUPLICATE_CYCLE_OK", commands["cycle_duplicate"]["ok"], "Duplicate cycle should succeed.", commands["cycle_duplicate"])
        check(checks, "DUPLICATE_ORDER_NOT_CREATED", dict_size(map_before) == 1 and dict_size(map_after) == 1, "Execution map size should remain 1.", {"before": map_before, "after": map_after})

        print("[final] reset verification")
        commands["reset_final"] = run_reset()
        check(checks, "RESET_FINAL_OK", commands["reset_final"]["ok"], "Final reset should succeed.", commands["reset_final"])
        validate_reset(checks)

        print("[final] build result")
        result = build_result(started, now(), checks, commands)
        save_json(RESULT_PATH, result)
        append_json_log(LOG_PATH, result)
        print_result(result)

        if result["status"] != "PASSED":
            sys.exit(1)

    except Exception as error:
        result = {
            "step": "STEP_50_FULL_REGRESSION_TEST",
            "status": "ERROR",
            "started_at_utc": started,
            "finished_at_utc": now(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "checks": checks,
            "commands": commands,
        }
        save_json(RESULT_PATH, result)
        append_json_log(LOG_PATH, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)


def test_env(bridge: bool) -> Dict[str, str]:
    return {
        "BOT_MODE": "PAPER_ONLY",
        "SYMBOL": "BTCUSDT",
        "TELEGRAM_ENABLED": "false",
        "ALLOW_SYNTHETIC_MARKET_CONTEXT": "true",
        "SYNTHETIC_CURRENT_PRICE": "106850",
        "LIVE_TRADING_ENABLED": "false",
        "EXCHANGE_MODE": "MOCK",
        "ORDER_EXECUTOR_INTEGRATION_ENABLED": "true" if bridge else "false",
        "EXCHANGE_ORDER_ENABLED": "true" if bridge else "false",
        "ORDER_EXECUTOR_QUANTITY": "0.00005",
        "MAX_ORDER_USDT": "10",
        "MAX_POSITION_USDT": "10",
        "MAX_OPEN_POSITIONS": "1",
        "MAX_RECENT_LOSSES": "3",
        "FALLBACK_TRIGGER_PRICE": "107500",
        "FALLBACK_INVALIDATION_PRICE": "106200",
        "FALLBACK_TAKE_PROFIT": "110000",
        "FALLBACK_SETUP_TYPE": "breakout_reclaim",
        "FALLBACK_SETUP_DIRECTION": "long",
        "FALLBACK_EXPIRES_AFTER_HOURS": "24",
    }


def run_script(script: str, env_overrides: Dict[str, str]) -> Dict[str, Any]:
    env = os.environ.copy()
    env.update(env_overrides)
    proc = subprocess.run([sys.executable, script], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"script": script, "return_code": proc.returncode, "ok": proc.returncode == 0, "stdout_tail": tail(proc.stdout), "stderr_tail": tail(proc.stderr)}



def run_reset() -> Dict[str, Any]:
    removed = []
    for name in RESET_FILES:
        path = STORAGE_DIR / name
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return {"script": "reset_paper_state.py", "return_code": 0, "ok": True, "removed_count": len(removed), "removed": removed[-20:]}

def validate_kb(checks: List[Dict[str, Any]]) -> None:
    required = [
        KNOWLEDGE_BASE_DIR / ".raw",
        KNOWLEDGE_BASE_DIR / "wiki" / "hot.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "index.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "log.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "source" / "coinalyze.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "entity" / "BTC.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "concept" / "open_interest.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "concept" / "funding_rate.md",
        KNOWLEDGE_BASE_DIR / "wiki" / "scenario" / "btc_short_squeeze_scenario.md",
        LINT_DIR / "kb_lint_result.json",
    ]
    for path in required:
        check(checks, f"KB_EXISTS::{path.relative_to(PROJECT_ROOT)}", path.exists(), "Required KB file/path should exist.", {"path": str(path)})
    daily_reports = list((KNOWLEDGE_BASE_DIR / "wiki" / "report" / "daily").glob("*.md"))
    lint = load_json(LINT_DIR / "kb_lint_result.json", {})
    check(checks, "KB_DAILY_REPORT_EXISTS", len(daily_reports) > 0, "At least one daily report should exist.", [str(p) for p in daily_reports])
    check(checks, "KB_LINT_PASSED", lint.get("status") == "PASSED", "KB lint should pass.", lint)


def validate_research_decision(checks: List[Dict[str, Any]]) -> None:
    decision = load_json(STORAGE_DIR / "research_decision.json", {})
    setup = decision.get("conditional_setup") if isinstance(decision, dict) else None
    check(checks, "RESEARCH_DECISION_EXISTS", (STORAGE_DIR / "research_decision.json").exists(), "research_decision.json should exist.", decision)
    check(checks, "RESEARCH_DECISION_HAS_SETUP", isinstance(setup, dict) and bool(setup), "Research decision should contain conditional_setup.", setup)
    for key in ["setup_type", "direction", "trigger_price", "invalidation_price", "take_profit"]:
        check(checks, f"RESEARCH_SETUP_FIELD::{key}", isinstance(setup, dict) and setup.get(key) is not None, f"conditional_setup should contain {key}.", setup)


def validate_reconciliation_checks(checks: List[Dict[str, Any]], reconciliation: Dict[str, Any]) -> None:
    expected = {"EXECUTION_EXISTS", "LIVE_ORDER_NOT_EXECUTED", "POSITION_ID_EXISTS", "POSITION_ID_MATCH", "EXECUTION_MAP_EXISTS", "EXECUTION_STATUS_VALID", "RISK_APPROVED", "ORDER_SIDE_MATCH", "FILLED_PRICE_EXISTS", "FILLED_QUANTITY_EXISTS", "PRICE_DIFF_REASONABLE", "DUPLICATE_EXECUTION_NOT_FOUND"}
    items = reconciliation.get("checks", [])
    by_name = {item.get("name"): item for item in items if isinstance(item, dict)} if isinstance(items, list) else {}
    for name in sorted(expected):
        item = by_name.get(name, {})
        check(checks, f"RECONCILIATION::{name}", item.get("passed") is True, f"Reconciliation check {name} should pass.", item)
    failed = reconciliation.get("failed_checks", [])
    check(checks, "RECONCILIATION_FAILED_EMPTY", isinstance(failed, list) and len(failed) == 0, "Reconciliation failed_checks should be empty.", failed)


def validate_reset(checks: List[Dict[str, Any]]) -> None:
    empty_files = ["paper_watchlist.json", "paper_positions.json", "paper_trade_history.json", "paper_order_execution_map.json"]
    missing_or_empty_files = ["risk_check_result.json", "order_execution_result.json", "exchange_router_result.json", "mock_order_result.json", "execution_reconciliation_result.json"]
    for name in empty_files:
        value = load_json(STORAGE_DIR / name, [])
        check(checks, f"RESET_EMPTY::{name}", is_empty(value), f"{name} should be empty after reset.", value)
    for name in missing_or_empty_files:
        path = STORAGE_DIR / name
        value = load_json(path, {})
        check(checks, f"RESET_MISSING_OR_EMPTY::{name}", (not path.exists()) or is_empty(value), f"{name} should be missing or empty after reset.", {"exists": path.exists(), "value": value})


def write_market_context(price: float) -> None:
    save_json(MARKET_CONTEXT_PATH, {"symbol": "BTCUSDT", "current_price": price, "price": price, "source": "full_regression_test", "timestamp_utc": now()})


def bridge_status(cycle: Dict[str, Any]) -> Any:
    trading = cycle.get("trading_summary", {}) if isinstance(cycle.get("trading_summary"), dict) else {}
    return trading.get("order_executor_bridge_status")


def reconciliation_status() -> Any:
    return load_json(STORAGE_DIR / "execution_reconciliation_result.json", {}).get("status")


def live_order_executed(order_execution: Dict[str, Any], router: Dict[str, Any], mock: Dict[str, Any]) -> bool:
    if isinstance(order_execution.get("safety"), dict) and order_execution["safety"].get("live_order_executed") is True:
        return True
    if isinstance(mock.get("raw_response"), dict) and mock["raw_response"].get("live_order_executed") is True:
        return True
    order_result = router.get("order_result")
    if isinstance(order_result, dict) and isinstance(order_result.get("raw_response"), dict):
        return order_result["raw_response"].get("live_order_executed") is True
    return False


def count(summary: Dict[str, Any], section: str, key: str) -> Any:
    obj = summary.get(section, {}) if isinstance(summary.get(section), dict) else {}
    return obj.get(key)


def check(checks: List[Dict[str, Any]], name: str, passed: bool, message: str, details: Any = None) -> None:
    checks.append({"name": name, "passed": bool(passed), "message": message, "details": details if details is not None else {}, "timestamp_utc": now()})


def build_result(started: str, finished: str, checks: List[Dict[str, Any]], commands: Dict[str, Any]) -> Dict[str, Any]:
    failed = [item for item in checks if item.get("passed") is not True]
    return {
        "step": "STEP_50_FULL_REGRESSION_TEST",
        "status": "PASSED" if not failed else "FAILED",
        "started_at_utc": started,
        "finished_at_utc": finished,
        "summary": {"total_checks": len(checks), "passed_checks": len(checks) - len(failed), "failed_checks": len(failed)},
        "checks": checks,
        "failed_checks": failed,
        "commands": commands,
        "safety": {"live_trading_enabled": False, "exchange_mode": "MOCK", "telegram_enabled": False},
    }


def print_result(result: Dict[str, Any]) -> None:
    summary = result.get("summary", {})
    print("=" * 80)
    print("[FULL REGRESSION RESULT]")
    print(f"Status: {result.get('status')}")
    print(f"Total Checks: {summary.get('total_checks')}")
    print(f"Passed: {summary.get('passed_checks')}")
    print(f"Failed: {summary.get('failed_checks')}")
    print("-" * 80)
    if result.get("failed_checks"):
        for item in result["failed_checks"]:
            print(f"- {item.get('name')}: {item.get('message')}")
    else:
        print("Failed Checks: None")
    print("=" * 80)


def dict_size(value: Any) -> int:
    return len(value) if isinstance(value, dict) else 0


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (dict, list, tuple, set, str)) and len(value) == 0)


def tail(text: str, max_lines: int = 80) -> str:
    return "\n".join((text or "").splitlines()[-max_lines:])


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
