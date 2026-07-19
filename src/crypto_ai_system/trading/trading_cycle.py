from __future__ import annotations

from config.settings import MARKET_SNAPSHOT_PATH, TRADING_CYCLE_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.trading.signal_engine import generate_trading_signal
from crypto_ai_system.trading.permission_audit import log_permission_gate_audit
from crypto_ai_system.trading.paper_report import build_and_save_paper_risk_level_report


TRADING_CYCLE_MODE = "PAPER_SHADOW_DECISION_ONLY"
ORDER_EXECUTION_ENABLED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False

# The paper position lifecycle is owned by execution.paper_position_kernel (run
# from the trading agent); the legacy Path A book (paper_engine.run_paper_cycle)
# is retired and no longer called here. The audit record keeps the delegation
# marker so its schema stays stable across that retirement.
_KERNEL_DELEGATION = {"status": "DELEGATED_TO_KERNEL", "active_position": None}


def run_trading_cycle(allow_new_position: bool = True) -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    if not snapshot:
        raise RuntimeError("No market snapshot found.")

    signal = generate_trading_signal()
    effective_allow_new_position = bool(allow_new_position and signal.get("allow_new_position", True))

    permission_audit = log_permission_gate_audit(signal, _KERNEL_DELEGATION, snapshot)
    paper_risk_level_report = build_and_save_paper_risk_level_report()

    result = {
        "created_at": utc_now_iso(),
        "symbol": snapshot.get("symbol"),
        "trading_signal": signal,
        "allow_new_position": effective_allow_new_position,
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
        "risk_level": signal.get("risk_level"),
        "permission_gate_applied": signal.get("permission_gate_applied", False),
    })
    return result


def main() -> None:
    result = run_trading_cycle()
    print(f"Trading cycle: {result['trading_signal']['signal']}")


if __name__ == "__main__":
    main()
