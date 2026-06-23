from __future__ import annotations

from core.json_io import read_storage_json, write_storage_json
from core.time_utils import utc_now_iso
from core.console import configure_utf8_console, safe_print


def run_dynamic_setup() -> dict:
    snapshot = read_storage_json("market_snapshot.json", default={})
    if not snapshot:
        raise RuntimeError("Missing market_snapshot.json. Run build_market_snapshot.py first.")

    volatility_proxy = abs(float(snapshot.get("change_24h_pct", 0.0)))
    risk_per_trade = 0.005 if volatility_proxy > 3 else 0.01
    result = {
        "schema_version": "step80.dynamic_setup.v1",
        "generated_at": utc_now_iso(),
        "risk_per_trade": risk_per_trade,
        "position_mode": "paper_only",
        "notes": ["Step80 dynamic setup is intentionally conservative."],
    }
    write_storage_json("dynamic_setup_result.json", result)
    return result


def main() -> None:
    configure_utf8_console()
    result = run_dynamic_setup()
    safe_print("Dynamic setup:", result)


if __name__ == "__main__":
    main()
