from __future__ import annotations

from config.settings import MARKET_CONTEXT_PATH, MARKET_SNAPSHOT_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def build_market_context() -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    if not snapshot:
        raise RuntimeError("No market snapshot found. Run build_market_snapshot first.")

    positives = []
    risks = []

    if snapshot.get("trend_bias") == "bullish":
        positives.append("bullish_market_structure")
    if float(snapshot.get("change_24h_pct", 0)) > 1:
        positives.append("positive_24h_momentum")
    if float(snapshot.get("volume_ratio", 1)) > 1.2:
        positives.append("above_average_volume")

    if snapshot.get("trend_bias") == "bearish":
        risks.append("bearish_market_structure")
    if abs(float(snapshot.get("funding_rate", 0))) > 0.001:
        risks.append("funding_extreme")
    if snapshot.get("is_synthetic") or snapshot.get("is_fallback"):
        risks.append("synthetic_or_fallback_data_source")

    summary = "Constructive" if len(positives) > len(risks) else "Cautious"
    context = {
        "created_at": utc_now_iso(),
        "summary": summary,
        "positives": positives,
        "risks": risks,
        "snapshot": snapshot,
    }
    atomic_write_json(MARKET_CONTEXT_PATH, context)
    log_event("market_context_built", {"summary": summary, "risk_count": len(risks)})
    return context


def main() -> None:
    context = build_market_context()
    print(f"Market context built: {context['summary']}")


if __name__ == "__main__":
    main()
