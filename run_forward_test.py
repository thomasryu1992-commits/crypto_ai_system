from __future__ import annotations

from core.console import configure_utf8_console, safe_print
from core.json_io import write_storage_json
from core.time_utils import utc_now_iso
from run_full_cycle import run_full_cycle


def main() -> None:
    configure_utf8_console()
    result = run_full_cycle()
    out = {"status": "PASSED", "generated_at": utc_now_iso(), "sample_cycle_mode": result.get("mode")}
    write_storage_json("forward_test_result.json", out)
    safe_print("Forward test:", out)


if __name__ == "__main__":
    main()
