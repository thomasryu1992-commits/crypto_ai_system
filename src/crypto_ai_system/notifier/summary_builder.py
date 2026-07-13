from __future__ import annotations

from typing import Dict, Any

from crypto_ai_system.research.report_renderer import render_daily_summary
from crypto_ai_system.notifier.telegram import build_telegram_message


def build_daily_notification(research_result: Dict[str, Any], trade_decision: Dict[str, Any] | None = None) -> str:
    summary = render_daily_summary(research_result)
    plan = None
    if trade_decision:
        plan = trade_decision.get('trade_plan')
    return build_telegram_message(summary, plan, trade_decision=trade_decision)
