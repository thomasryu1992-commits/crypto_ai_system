from __future__ import annotations

import compileall

from core.console import configure_utf8_console, safe_print
from core.json_io import write_storage_json
from core.time_utils import utc_now_iso
from run_operational_dry_run import run_operational_dry_run


def main() -> None:
    configure_utf8_console()
    compile_ok = compileall.compile_dir(".", quiet=1)
    dry_run = run_operational_dry_run()
    status = "PASSED" if compile_ok and dry_run.get("status") == "PASSED" else "FAILED"
    out = {"status": status, "compile_ok": compile_ok, "dry_run_status": dry_run.get("status"), "generated_at": utc_now_iso()}
    write_storage_json("full_regression_test_result.json", out)
    safe_print("Full regression test:", out)


if __name__ == "__main__":
    main()
