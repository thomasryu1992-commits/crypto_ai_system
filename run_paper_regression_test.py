from __future__ import annotations

from core.console import configure_utf8_console, safe_print
from core.json_io import write_storage_json
from core.time_utils import utc_now_iso
from trading.paper_engine import run_paper_engine


def main() -> None:
    configure_utf8_console()
    sample = {"signal": "LONG", "confidence": 80, "snapshot": {"last_close": 65000}, "reasons": ["regression sample"]}
    state = run_paper_engine(sample)
    out = {"status": "PASSED", "generated_at": utc_now_iso(), "active_position": bool(state.get("active_position"))}
    write_storage_json("paper_regression_test_result.json", out)
    safe_print("Paper regression test:", out)


if __name__ == "__main__":
    main()
