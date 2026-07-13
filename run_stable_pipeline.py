from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COMMANDS = [
    ("storage permission fix", [sys.executable, "fix_storage_permissions.py"]),
    ("Step150 safety validation", [sys.executable, "run_step150_validation.py"]),
    ("Step157E full validation", [sys.executable, "run_step157e_full_validation.py"]),
    ("operational dry run", [sys.executable, "run_operational_dry_run.py"]),
    ("spreadsheet/local backup sync", [sys.executable, "run_spreadsheet_sync.py"]),
    ("system health check", [sys.executable, "run_system_health_check.py"]),
]


def run_command(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label} ===")
    completed = subprocess.run(cmd, cwd=ROOT)
    if completed.returncode != 0:
        print(f"FAILED: {label} / returncode={completed.returncode}")
        return False
    print(f"OK: {label}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the stable Step1~157E Extended pipeline.")
    parser.add_argument("--send-telegram", action="store_true", help="Send scheduler health report after local health check.")
    args = parser.parse_args()

    ok = True
    for label, cmd in COMMANDS:
        ok = run_command(label, cmd) and ok

    if args.send_telegram:
        ok = run_command("Telegram scheduler health report", [sys.executable, "send_scheduler_health_report.py"]) and ok

    print("\n=== Stable pipeline result ===")
    print("PASSED" if ok else "FAILED")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
