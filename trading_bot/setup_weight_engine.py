from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from scripts.json_utils import load_json, now_utc_iso, save_json, to_float


def build_setup_weight_report(storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    setup_report = load_json(storage_path / "setup_performance_report.json", default={})
    setups = setup_report.get("setups", []) if isinstance(setup_report, dict) else []
    if not isinstance(setups, list):
        setups = []
    weighted = [_weight_setup(item) for item in setups if isinstance(item, dict)]
    report = {
        "status": "SETUP_WEIGHT_UPDATED",
        "timestamp_utc": now_utc_iso(),
        "setups": weighted,
        "setup_count": len(weighted),
        "tradable_setup_count": sum(1 for s in weighted if s.get("setup_weight_decision") == "TRADABLE"),
        "observe_only_setup_count": sum(1 for s in weighted if s.get("setup_weight_decision") == "OBSERVE_ONLY"),
        "disabled_setup_count": sum(1 for s in weighted if s.get("setup_weight_decision") == "DISABLED"),
    }
    save_json(storage_path / "setup_weight_report.json", report)
    return report


def _weight_setup(item: Dict[str, Any]) -> Dict[str, Any]:
    total = int(item.get("total_trades") or 0)
    win_rate = to_float(item.get("win_rate_pct")) or 0.0
    avg = to_float(item.get("average_pnl_pct")) or 0.0
    expectancy = avg
    win_component = min(max(win_rate / 100, 0), 1)
    pnl_component = min(max((avg + 2) / 4, 0), 1)
    data_component = min(total / 20, 1)
    final_weight = round((win_component * 0.4) + (pnl_component * 0.4) + (data_component * 0.2), 4)
    decision = _classify_weight_decision(total, avg, expectancy, final_weight)
    return {**item, "expectancy_score": round(expectancy, 6), "final_weight": final_weight, "setup_weight_decision": decision}


def _classify_weight_decision(total_trades: int, average_pnl: float, expectancy_score: float, final_weight: float) -> str:
    if total_trades >= 10 and average_pnl < 0:
        return "DISABLED"
    if total_trades >= 5 and final_weight <= 0.4:
        return "DISABLED"
    if total_trades < 5:
        return "OBSERVE_ONLY"
    if average_pnl > 0 and expectancy_score >= 0:
        return "TRADABLE"
    return "OBSERVE_ONLY"
