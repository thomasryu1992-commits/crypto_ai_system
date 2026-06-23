from __future__ import annotations

import compileall
import subprocess
import sys


def main() -> int:
    compile_ok = compileall.compile_dir(".", quiet=1)
    if not compile_ok:
        print("compileall failed")
        return 1
    result = subprocess.run([sys.executable, "run_operational_dry_run.py"], check=False)
    if result.returncode != 0:
        print("operational dry run failed")
        return result.returncode
    print("Step80 validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
