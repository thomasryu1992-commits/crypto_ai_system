from __future__ import annotations

from config.settings import MARKET_SNAPSHOT_PATH, RESEARCH_RESULT_PATH, TRADING_CYCLE_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.trading.signal_engine import generate_trading_signal
from crypto_ai_system.trading.paper_engine import run_paper_cycle
from crypto_ai_system.trading.permission_audit import log_permission_gate_audit
from crypto_ai_system.trading.paper_report import build_and_save_paper_risk_level_report


TRADING_CYCLE_MODE = "PAPER_SHADOW_DECISION_ONLY"
ORDER_EXECUTION_ENABLED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False


def run_trading_cycle(allow_new_position: bool = True) -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    if not snapshot:
        raise RuntimeError("No market snapshot found.")

    signal = generate_trading_signal()
    effective_allow_new_position = bool(allow_new_position and signal.get("allow_new_position", True))
    paper_result = run_paper_cycle(signal, snapshot, allow_new_position=effective_allow_new_position)

    permission_audit = log_permission_gate_audit(signal, paper_result, snapshot)
    paper_risk_level_report = build_and_save_paper_risk_level_report()

    result = {
        "created_at": utc_now_iso(),
        "symbol": snapshot.get("symbol"),
        "trading_signal": signal,
        "paper_result": paper_result,
        "permission_gate": {
            "applied": bool(signal.get("permission_gate_applied", False)),
            "allow_long": bool(signal.get("allow_long", False)),
            "allow_short": bool(signal.get("allow_short", False)),
            "allow_new_position": bool(signal.get("allow_new_position", False)),
            "risk_level": signal.get("risk_level"),
            "position_size_multiplier": signal.get("position_size_multiplier"),
            "research_signal_id": signal.get("research_signal_id"),
            "block_reasons": signal.get("block_reasons", []),
            "risk_warnings": signal.get("risk_warnings", []),
        },
        "permission_gate_audit": permission_audit,
        "paper_risk_level_report": paper_risk_level_report,
        "trading_cycle_mode": TRADING_CYCLE_MODE,
        "order_execution_enabled_by_this_module": ORDER_EXECUTION_ENABLED_BY_THIS_MODULE,
        "live_trading_allowed_by_this_module": LIVE_TRADING_ALLOWED_BY_THIS_MODULE,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
    }
    atomic_write_json(TRADING_CYCLE_PATH, result)
    log_event("trading_cycle_completed", {
        "signal": signal.get("signal"),
        "paper_status": paper_result.get("status"),
        "risk_level": signal.get("risk_level"),
        "permission_gate_applied": signal.get("permission_gate_applied", False),
    })
    return result


def main() -> None:
    result = run_trading_cycle()
    print(f"Trading cycle: {result['trading_signal']['signal']} paper={result['paper_result']['status']}")


if __name__ == "__main__":
    main()
