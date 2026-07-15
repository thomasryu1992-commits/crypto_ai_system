"""Aggregate scheduler cycle metrics + the performance report into a dashboard.

Pure and testable: :func:`build_dashboard` takes the list of per-cycle metric
records (as the scheduler logs them) and the latest performance report, and
returns a compact status board with health warnings. The CLI in
``scripts/dashboard.py`` renders it.
"""

from __future__ import annotations

from typing import Any

# Warning thresholds.
MIN_SAMPLE_FOR_EXPECTANCY = 3
STALE_DATA_RATE_WARN = 0.10
SIGNAL_DRIFT_WARN = 0.50
RECENT_WINDOW = 10


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_warnings(records: list[dict], report: dict) -> list[str]:
    warnings: list[str] = []
    closed = int(_num(report.get("closed_count"), 0))

    if closed >= MIN_SAMPLE_FOR_EXPECTANCY and _num(report.get("expectancy")) < 0:
        warnings.append("negative_expectancy")
    if _num(report.get("stale_data_rate")) > STALE_DATA_RATE_WARN:
        warnings.append("elevated_stale_data_rate")
    if abs(_num(report.get("signal_to_outcome_drift"))) > SIGNAL_DRIFT_WARN:
        warnings.append("signal_to_outcome_drift")
    if int(_num(report.get("reconciliation_mismatch_count"), 0)) > 0:
        warnings.append("reconciliation_mismatch")

    recent = records[-RECENT_WINDOW:]
    if any(not r.get("ok", True) for r in recent):
        warnings.append("recent_cycle_errors")
    if any(r.get("data_is_synthetic") for r in recent):
        warnings.append("running_on_synthetic_data")
    return warnings


def build_dashboard(records: list[dict], report: dict) -> dict:
    report = report or {}
    ok_records = [r for r in records if r.get("ok", True)]
    error_records = [r for r in records if not r.get("ok", True)]
    trades = sum(1 for r in ok_records if r.get("trade_executed"))
    synthetic = sum(1 for r in ok_records if r.get("data_is_synthetic"))
    timestamps = [r.get("ts") for r in records if r.get("ts")]

    return {
        "cycles": len(records),
        "ok_cycles": len(ok_records),
        "error_cycles": len(error_records),
        "ok_rate": _rate(len(ok_records), len(records)),
        "trades_placed": trades,
        "synthetic_cycles": synthetic,
        "first_cycle_at": timestamps[0] if timestamps else None,
        "last_cycle_at": timestamps[-1] if timestamps else None,
        "performance": {
            "status": report.get("status"),
            "sample_size": report.get("sample_size"),
            "closed_count": report.get("closed_count"),
            "expectancy": report.get("expectancy"),
            "win_loss_ratio": report.get("win_loss_ratio"),
            "average_R": report.get("average_R"),
            "max_drawdown": report.get("max_drawdown"),
            "live_candidate_eligible": report.get("live_candidate_eligible"),
        },
        "warnings": build_warnings(records, report),
    }
