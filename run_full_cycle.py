from __future__ import annotations

from collectors.market_data_collector import collect_market_data
from builders.market_snapshot import build_market_snapshot
from builders.market_context import build_market_context
from research.research_engine import run_research_cycle
from research.decision_engine import run_research_decision
from data_health.health_check import run_data_health_check
from risk.risk_guard import run_risk_guard
from trading.trading_cycle import run_trading_cycle
from bridge.research_trading_bridge import run_research_trading_bridge
from execution.order_executor import run_order_executor
from execution.reconciler import run_reconciler
from analysis.live_shadow import run_live_shadow_report
from reports.limited_live_readiness import build_limited_live_readiness_report
from integrations.spreadsheet_exporter import export_spreadsheet_schema_v3


def run_full_cycle() -> dict:
    collect_market_data()
    build_market_snapshot()
    build_market_context()
    research = run_research_cycle()
    research_decision = run_research_decision()
    data_health = run_data_health_check()
    risk = run_risk_guard()
    trading = run_trading_cycle(allow_new_position=data_health.get("allow_trading") and risk.get("allow_new_position"))
    trade_decision = run_research_trading_bridge()
    order = run_order_executor()
    reconciliation = run_reconciler()
    shadow = run_live_shadow_report()
    limited_live = build_limited_live_readiness_report()
    spreadsheet = export_spreadsheet_schema_v3()
    return {
        "research": research,
        "research_decision": research_decision,
        "data_health": data_health,
        "risk": risk,
        "trading": trading,
        "trade_decision": trade_decision,
        "order": order,
        "reconciliation": reconciliation,
        "shadow": shadow,
        "limited_live": limited_live,
        "spreadsheet": spreadsheet,
    }


def main() -> None:
    result = run_full_cycle()
    print("Full cycle completed.")
    print("Decision:", result["trade_decision"]["final_decision"])
    print("Data health:", result["data_health"]["status"])
    print("Order:", result["order"]["status"])
    print("Spreadsheet:", result["spreadsheet"]["status"])


if __name__ == "__main__":
    main()
