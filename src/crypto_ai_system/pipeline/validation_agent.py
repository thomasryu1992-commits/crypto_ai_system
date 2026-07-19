"""Validation agent: data health + risk guard -> allow-trading gate.

This is the cold-path gate. It never places orders; it decides whether the
trading agent is permitted to open a new position this cycle. A no-trade
verdict is DEGRADED (the loop keeps running, feedback still learns), not a
fatal halt. The hot-path PreOrderRiskGate runs later, inside the trading
agent, immediately before any real order.
"""

from __future__ import annotations

from data_health.health_check import run_data_health_check
from risk.risk_guard import run_risk_guard

from crypto_ai_system.pipeline.base import Agent
from crypto_ai_system.pipeline.contracts import PipelineContext, StageResult


class ValidationAgent(Agent):
    name = "validation"
    fatal_on_error = True

    def execute(self, ctx: PipelineContext) -> StageResult:
        data_health = run_data_health_check()
        risk = run_risk_guard()

        health_ok = bool(data_health.get("allow_trading"))
        risk_ok = bool(risk.get("allow_new_position"))
        allow_new_position = health_ok and risk_ok

        outputs = {
            "data_health": data_health,
            "risk_status": risk,
            "allow_new_position": allow_new_position,
        }

        # Multibook observability (None when disabled): capacity pressure is
        # visible here before the book kernel starts refusing opens. Best-effort
        # — a report failure must never gate trading.
        try:
            from crypto_ai_system.execution.paper_book_kernel import multibook_report

            report = multibook_report()
            if report is not None:
                outputs["multibook"] = report
        except Exception:  # noqa: BLE001 - observational only
            pass

        if allow_new_position:
            return self.ok(**outputs)

        reasons = []
        if not health_ok:
            reasons.append("data health gate blocked trading")
        if not risk_ok:
            reasons.append("risk guard blocked new position")
        return self.degraded(reasons, **outputs)
