from __future__ import annotations

from config.settings import MARKET_SNAPSHOT_PATH, RESEARCH_RESULT_PATH, TRADING_CYCLE_PATH
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from trading.signal_engine import generate_trading_signal
from trading.paper_engine import run_paper_cycle


def run_trading_cycle(allow_new_position: bool = True) -> dict:
    snapshot = read_json(MARKET_SNAPSHOT_PATH, {})
    if not snapshot:
        raise RuntimeError("No market snapshot found.")

    signal = generate_trading_signal()
    paper_result = run_paper_cycle(signal, snapshot, allow_new_position=allow_new_position)

    result = {
        "created_at": utc_now_iso(),
        "symbol": snapshot.get("symbol"),
        "trading_signal": signal,
        "paper_result": paper_result,
    }
    atomic_write_json(TRADING_CYCLE_PATH, result)
    log_event("trading_cycle_completed", {"signal": signal.get("signal"), "paper_status": paper_result.get("status")})
    return result


def main() -> None:
    result = run_trading_cycle()
    print(f"Trading cycle: {result['trading_signal']['signal']} paper={result['paper_result']['status']}")


if __name__ == "__main__":
    main()
