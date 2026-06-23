from __future__ import annotations

import subprocess
import sys
import time

from config.settings import STORAGE_DIR, env_int, env_str, ensure_base_dirs
from scripts.json_utils import append_json_log, now_utc_iso, save_json


def main() -> None:
    ensure_base_dirs()
    interval = env_int("FORWARD_TEST_INTERVAL_SECONDS", 300)
    max_cycles = env_int("FORWARD_TEST_MAX_CYCLES", 12)
    target = env_str("FORWARD_TEST_TARGET", "TRADING_CYCLE").upper()
    command = [sys.executable, "run_full_cycle.py"] if target == "FULL_CYCLE" else [sys.executable, "run_trading_cycle.py"]
    results = []
    for i in range(max_cycles):
        proc = subprocess.run(command, cwd=str(STORAGE_DIR.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
        item = {"cycle": i + 1, "timestamp_utc": now_utc_iso(), "return_code": proc.returncode, "stdout_tail": proc.stdout[-3000:], "stderr_tail": proc.stderr[-3000:]}
        results.append(item)
        append_json_log(STORAGE_DIR / "forward_test_log.json", item)
        print(f"[FORWARD TEST] cycle={i+1}/{max_cycles} return_code={proc.returncode}")
        if i < max_cycles - 1:
            time.sleep(interval)
    result = {"status": "FORWARD_TEST_COMPLETED", "target": target, "cycles": results}
    save_json(STORAGE_DIR / "forward_test_result.json", result)


if __name__ == "__main__":
    main()
