from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from scripts.json_utils import load_json, now_utc_iso, save_json, to_float


def analyze_setup_performance(storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    history = load_json(storage_path / "paper_trade_history.json", default=[])
    if not isinstance(history, list):
        history = []
    grouped: Dict[str, List[float]] = defaultdict(list)
    for trade in history:
        if not isinstance(trade, dict):
            continue
        setup_type = str(trade.get("setup_type") or "unknown")
        grouped[setup_type].append(to_float(trade.get("realized_pnl_pct")) or 0.0)
    setups = []
    for setup_type, pnls in sorted(grouped.items()):
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        setups.append({
            "setup_type": setup_type,
            "total_trades": len(pnls),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": round((len(wins) / len(pnls)) * 100, 4) if pnls else 0.0,
            "total_pnl_pct": round(sum(pnls), 6),
            "average_pnl_pct": round(sum(pnls) / len(pnls), 6) if pnls else 0.0,
        })
    report = {"status": "SETUP_PERFORMANCE_UPDATED", "timestamp_utc": now_utc_iso(), "setups": setups, "setup_count": len(setups)}
    save_json(storage_path / "setup_performance_report.json", report)
    return report
