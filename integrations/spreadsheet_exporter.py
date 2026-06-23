from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from integrations.google_sheets_client import sync_rows_to_google_sheet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
LINT_DIR = KNOWLEDGE_BASE_DIR / "lint"
BASE_EXPORT_DIR = STORAGE_DIR / "spreadsheet_exports"

SYNC_RESULT_PATH = STORAGE_DIR / "spreadsheet_sync_result.json"
SYNC_LOG_PATH = STORAGE_DIR / "spreadsheet_sync_log.json"


def run_spreadsheet_sync() -> Dict[str, Any]:
    """
    Spreadsheet Export / Google Sheets Sync

    Always exports local CSV files into storage/spreadsheet_exports/.
    Optionally syncs the same tables to Google Sheets if GOOGLE_SHEETS_ENABLED=true.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    enabled = _env_bool("SPREADSHEET_EXPORT_ENABLED", True)
    export_dir = Path(os.getenv("SPREADSHEET_EXPORT_DIR", str(BASE_EXPORT_DIR)))
    if not export_dir.is_absolute():
        export_dir = PROJECT_ROOT / export_dir

    export_dir.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    if not enabled:
        result = {
            "step": "SPREADSHEET_EXPORT_SYNC",
            "status": "SKIPPED",
            "reason": "SPREADSHEET_EXPORT_ENABLED=false",
            "timestamp_utc": _now_utc_iso(),
        }
        _save_json(SYNC_RESULT_PATH, result)
        _append_log(SYNC_LOG_PATH, result)
        return result

    tables = build_spreadsheet_tables()
    csv_results = []
    google_results = []

    for sheet_name, rows in tables.items():
        csv_results.append(_write_csv(export_dir / f"{sheet_name}.csv", rows))
        google_results.append(sync_rows_to_google_sheet(sheet_name, rows, replace=True))

    failed_csv = [item for item in csv_results if item.get("status") != "EXPORTED"]
    google_errors = [item for item in google_results if item.get("status") == "ERROR"]

    status = "SYNC_COMPLETED"
    if failed_csv or google_errors:
        status = "SYNC_COMPLETED_WITH_ERRORS"

    result = {
        "step": "SPREADSHEET_EXPORT_SYNC",
        "status": status,
        "timestamp_utc": _now_utc_iso(),
        "summary": {
            "table_count": len(tables),
            "csv_export_count": len([item for item in csv_results if item.get("status") == "EXPORTED"]),
            "google_synced_count": len([item for item in google_results if item.get("status") == "SYNCED"]),
            "google_skipped_count": len([item for item in google_results if item.get("status") == "SKIPPED"]),
            "error_count": len(failed_csv) + len(google_errors),
        },
        "csv_results": csv_results,
        "google_results": google_results,
        "files": {
            "export_dir": str(export_dir),
            "spreadsheet_sync_result": str(SYNC_RESULT_PATH),
            "spreadsheet_sync_log": str(SYNC_LOG_PATH),
        },
    }

    _save_json(SYNC_RESULT_PATH, result)
    _append_log(SYNC_LOG_PATH, result)

    return result


def build_spreadsheet_tables() -> Dict[str, List[Dict[str, Any]]]:
    market_snapshot = _load_json(STORAGE_DIR / "market_snapshot.json", default={})
    market_context = _load_json(STORAGE_DIR / "market_context.json", default={})
    research_decision = _load_json(STORAGE_DIR / "research_decision.json", default={})
    trading_cycle = _load_json(STORAGE_DIR / "trading_cycle_result.json", default={})
    trading_bot = _load_json(STORAGE_DIR / "trading_bot_result.json", default={})
    bot_state = _load_json(STORAGE_DIR / "bot_state.json", default={})
    paper_trade_history = _load_json(STORAGE_DIR / "paper_trade_history.json", default=[])
    paper_performance = _load_json(STORAGE_DIR / "paper_performance_report.json", default={})
    setup_performance = _load_json(STORAGE_DIR / "setup_performance_report.json", default={})
    setup_weight = _load_json(STORAGE_DIR / "setup_weight_report.json", default={})
    risk_check = _load_json(STORAGE_DIR / "risk_check_result.json", default={})
    order_execution = _load_json(STORAGE_DIR / "order_execution_result.json", default={})
    reconciliation = _load_json(STORAGE_DIR / "execution_reconciliation_result.json", default={})
    kb_lint = _load_json(LINT_DIR / "kb_lint_result.json", default={})

    return {
        "dashboard_summary": [_dashboard_row(market_context, market_snapshot, research_decision, trading_cycle, trading_bot, bot_state, paper_performance, setup_weight, risk_check, order_execution, reconciliation, kb_lint)],
        "market_snapshot": _flatten_to_rows(market_snapshot, prefix="market"),
        "research_decision": _flatten_to_rows(research_decision, prefix="decision"),
        "trading_cycle": _flatten_to_rows(trading_cycle, prefix="cycle"),
        "paper_trade_history": _list_to_rows(paper_trade_history),
        "paper_performance": _flatten_to_rows(paper_performance, prefix="performance"),
        "setup_performance": _flatten_to_rows(setup_performance, prefix="setup_performance"),
        "setup_weight": _flatten_to_rows(setup_weight, prefix="setup_weight"),
        "risk_check": _flatten_to_rows(risk_check, prefix="risk"),
        "order_execution": _flatten_to_rows(order_execution, prefix="order_execution"),
        "execution_reconciliation": _flatten_to_rows(reconciliation, prefix="reconciliation"),
        "kb_lint": _flatten_to_rows(kb_lint, prefix="kb_lint"),
    }


def _dashboard_row(
    market_context: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    research_decision: Dict[str, Any],
    trading_cycle: Dict[str, Any],
    trading_bot: Dict[str, Any],
    bot_state: Dict[str, Any],
    paper_performance: Dict[str, Any],
    setup_weight: Dict[str, Any],
    risk_check: Dict[str, Any],
    order_execution: Dict[str, Any],
    reconciliation: Dict[str, Any],
    kb_lint: Dict[str, Any],
) -> Dict[str, Any]:
    trading_summary = trading_cycle.get("trading_summary", {}) if isinstance(trading_cycle.get("trading_summary"), dict) else {}
    conditional_setup = research_decision.get("conditional_setup", {}) if isinstance(research_decision.get("conditional_setup"), dict) else {}
    market_data = market_snapshot.get("market_data", {}) if isinstance(market_snapshot.get("market_data"), dict) else {}

    return {
        "timestamp_utc": _now_utc_iso(),
        "symbol": market_context.get("symbol") or research_decision.get("symbol") or trading_bot.get("symbol"),
        "current_price": market_context.get("current_price") or market_snapshot.get("current_price"),
        "trading_cycle_status": trading_cycle.get("status"),
        "trading_bot_status": trading_summary.get("trading_bot_status") or trading_bot.get("status"),
        "decision_type": research_decision.get("decision_type"),
        "trading_bias": research_decision.get("trading_bias"),
        "confidence": research_decision.get("confidence"),
        "setup_type": conditional_setup.get("setup_type"),
        "direction": conditional_setup.get("direction"),
        "trigger_price": conditional_setup.get("trigger_price"),
        "invalidation_price": conditional_setup.get("invalidation_price"),
        "take_profit": conditional_setup.get("take_profit"),
        "price_signal": _nested(market_data, "price.signal"),
        "open_interest_signal": _nested(market_data, "open_interest.signal"),
        "funding_signal": _nested(market_data, "funding_rate.signal"),
        "long_short_signal": _nested(market_data, "long_short_ratio.signal"),
        "liquidation_signal": _nested(market_data, "liquidation.signal"),
        "kb_lint_status": kb_lint.get("status"),
        "kb_lint_error_count": kb_lint.get("error_count"),
        "kb_lint_warning_count": kb_lint.get("warning_count"),
        "bridge_status": trading_summary.get("order_executor_bridge_status") or trading_bot.get("order_executor_bridge_status"),
        "risk_status": risk_check.get("status"),
        "order_execution_status": order_execution.get("status"),
        "reconciliation_status": reconciliation.get("status"),
        "reconciled": reconciliation.get("reconciled"),
        "bot_lifecycle_state": bot_state.get("lifecycle_state"),
        "total_trades": paper_performance.get("total_trades"),
        "win_rate_pct": paper_performance.get("win_rate_pct"),
        "total_realized_pnl_pct": paper_performance.get("total_realized_pnl_pct"),
        "setup_weight_status": setup_weight.get("status"),
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = []
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)

        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in headers})

        return {"status": "EXPORTED", "path": str(path), "row_count": len(rows), "column_count": len(headers)}
    except Exception as error:
        return {"status": "ERROR", "path": str(path), "error_type": type(error).__name__, "error_message": str(error)}


def _flatten_to_rows(data: Any, prefix: str = "data") -> List[Dict[str, Any]]:
    if data is None or data == {} or data == []:
        return []

    if isinstance(data, list):
        return _list_to_rows(data)

    if not isinstance(data, dict):
        return [{"key": prefix, "value": data}]

    flat = _flatten_dict(data)
    return [{"key": key, "value": value} for key, value in flat.items()]


def _list_to_rows(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, list):
        return []
    rows = []
    for index, item in enumerate(data):
        if isinstance(item, dict):
            rows.append({"row_index": index, **_flatten_dict(item)})
        else:
            rows.append({"row_index": index, "value": item})
    return rows


def _flatten_dict(data: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, dict):
            items.update(_flatten_dict(value, new_key, sep=sep))
        elif isinstance(value, list):
            items[new_key] = json.dumps(value, ensure_ascii=False)
        else:
            items[new_key] = value
    return items


def _nested(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _append_log(path: Path, item: Dict[str, Any], max_items: int = 500) -> None:
    existing = _load_json(path, default=[])
    if not isinstance(existing, list):
        existing = []
    existing.append(item)
    _save_json(path, existing[-max_items:])


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
