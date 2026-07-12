from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from config.settings import LATEST_PERMISSION_GATE_AUDIT_PATH, PAPER_RISK_LEVEL_REPORT_PATH, PAPER_TRADES_PATH, PERMISSION_GATE_AUDIT_PATH
from core.json_io import atomic_write_json, read_json, read_jsonl
from core.time_utils import utc_now_iso

RISK_LEVELS = ("normal", "reduced", "blocked")


def _empty_bucket() -> dict[str, Any]:
    return {
        "audit_count": 0,
        "position_opened_count": 0,
        "blocked_count": 0,
        "no_signal_count": 0,
        "active_update_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "closed_trade_count": 0,
        "total_pnl_r": 0.0,
        "avg_pnl_r": 0.0,
        "last_signal": None,
        "last_paper_status": None,
    }


def _normalise_risk_level(value: Any) -> str:
    level = str(value or "normal").lower()
    return level if level in RISK_LEVELS else "normal"


def build_paper_risk_level_report_from_rows(
    audit_rows: Iterable[Mapping[str, Any]] | None,
    trades: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    buckets = {level: _empty_bucket() for level in RISK_LEVELS}
    audit_rows = [dict(row) for row in (audit_rows or [])]
    trades = [dict(row) for row in (trades or [])]

    for row in audit_rows:
        level = _normalise_risk_level(row.get("risk_level"))
        bucket = buckets[level]
        bucket["audit_count"] += 1
        status = str(row.get("paper_status") or "UNKNOWN")
        bucket["last_signal"] = row.get("signal")
        bucket["last_paper_status"] = status
        if status == "POSITION_OPENED" or row.get("position_opened") is True:
            bucket["position_opened_count"] += 1
        elif status == "BLOCKED_BY_PERMISSION_GATE":
            bucket["blocked_count"] += 1
        elif status == "NO_SIGNAL":
            bucket["no_signal_count"] += 1
        elif status == "ACTIVE_POSITION_UPDATED":
            bucket["active_update_count"] += 1

    for trade in trades:
        level = _normalise_risk_level(trade.get("risk_level"))
        bucket = buckets[level]
        status = str(trade.get("status") or "")
        result = str(trade.get("result") or "")
        if status == "CLOSED" or result in {"WIN", "LOSS", "BREAKEVEN"}:
            bucket["closed_trade_count"] += 1
            if result == "WIN":
                bucket["win_count"] += 1
            elif result == "LOSS":
                bucket["loss_count"] += 1
            try:
                bucket["total_pnl_r"] += float(trade.get("pnl_r") or 0.0)
            except Exception:
                pass

    for bucket in buckets.values():
        closed = int(bucket["closed_trade_count"])
        if closed > 0:
            bucket["avg_pnl_r"] = round(float(bucket["total_pnl_r"]) / closed, 4)
        bucket["total_pnl_r"] = round(float(bucket["total_pnl_r"]), 4)

    total_audit = sum(int(bucket["audit_count"]) for bucket in buckets.values())
    total_opened = sum(int(bucket["position_opened_count"]) for bucket in buckets.values())
    total_blocked = sum(int(bucket["blocked_count"]) for bucket in buckets.values())

    return {
        "created_at": utc_now_iso(),
        "status": "PAPER_RISK_LEVEL_REPORT_BUILT",
        "total_audit_records": total_audit,
        "total_position_opened": total_opened,
        "total_blocked_by_permission_gate": total_blocked,
        "by_risk_level": buckets,
        "latest_permission_gate": audit_rows[-1] if audit_rows else None,
    }


def build_and_save_paper_risk_level_report(
    *,
    audit_path: str | Path = PERMISSION_GATE_AUDIT_PATH,
    trades_path: str | Path = PAPER_TRADES_PATH,
    output_path: str | Path = PAPER_RISK_LEVEL_REPORT_PATH,
    latest_audit_path: str | Path = LATEST_PERMISSION_GATE_AUDIT_PATH,
) -> dict[str, Any]:
    rows = read_jsonl(audit_path)
    trades = read_json(trades_path, [])
    if not isinstance(trades, list):
        trades = []
    report = build_paper_risk_level_report_from_rows(rows, trades)
    if not report.get("latest_permission_gate"):
        latest = read_json(latest_audit_path, None)
        if isinstance(latest, dict):
            report["latest_permission_gate"] = latest
    atomic_write_json(output_path, report)
    return report
