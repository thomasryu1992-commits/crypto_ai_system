from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scripts.json_utils import load_json, now_utc_iso, save_json, to_float


def generate_paper_performance_report(storage_dir: str | Path = "storage") -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    history = load_json(storage_path / "paper_trade_history.json", default=[])
    if not isinstance(history, list):
        history = []
    pnls = [to_float(t.get("realized_pnl_pct")) or 0.0 for t in history if isinstance(t, dict)]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = len(pnls)
    report = {
        "status": "PAPER_PERFORMANCE_UPDATED",
        "timestamp_utc": now_utc_iso(),
        "total_trades": total,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round((len(wins) / total) * 100, 4) if total else 0.0,
        "total_realized_pnl_pct": round(sum(pnls), 6),
        "average_realized_pnl_pct": round(sum(pnls) / total, 6) if total else 0.0,
        "best_trade_pct": max(pnls) if pnls else 0.0,
        "worst_trade_pct": min(pnls) if pnls else 0.0,
    }
    save_json(storage_path / "paper_performance_report.json", report)
    return report
