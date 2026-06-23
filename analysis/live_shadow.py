from __future__ import annotations

from config.settings import (
    FEE_ASSUMPTION_BPS,
    LATENCY_ASSUMPTION_MS,
    LIVE_SHADOW_REPORT_PATH,
    ORDER_RESULT_PATH,
    SLIPPAGE_ASSUMPTION_BPS,
    TRADE_DECISION_PATH,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event


def run_live_shadow_report() -> dict:
    decision = read_json(TRADE_DECISION_PATH, {})
    order = read_json(ORDER_RESULT_PATH, {})
    roundtrip_cost = SLIPPAGE_ASSUMPTION_BPS * 2 + FEE_ASSUMPTION_BPS * 2

    report = {
        "created_at": utc_now_iso(),
        "mode": "LIVE_SHADOW",
        "decision": decision.get("final_decision"),
        "order_status": order.get("status"),
        "estimated_roundtrip_cost_bps": roundtrip_cost,
        "slippage_assumption_bps": SLIPPAGE_ASSUMPTION_BPS,
        "fee_assumption_bps": FEE_ASSUMPTION_BPS,
        "latency_assumption_ms": LATENCY_ASSUMPTION_MS,
        "live_ready": order.get("readiness", {}).get("ready", False),
        "notes": [
            "This is a shadow report only.",
            "No real exchange orders are placed by the guarded Step130 package.",
        ],
    }
    atomic_write_json(LIVE_SHADOW_REPORT_PATH, report)
    log_event("live_shadow_report_created", {"decision": report["decision"], "order_status": report["order_status"]})
    return report


def main() -> None:
    result = run_live_shadow_report()
    print(f"Live shadow report: order_status={result['order_status']} cost_bps={result['estimated_roundtrip_cost_bps']}")


if __name__ == "__main__":
    main()
