from __future__ import annotations

import sys

from integrations.spreadsheet_exporter import run_spreadsheet_sync


def main() -> None:
    result = run_spreadsheet_sync()

    print("=" * 80)
    print("[SPREADSHEET SYNC]")
    print("=" * 80)
    print(f"Status: {result.get('status')}")
    print(f"Summary: {result.get('summary')}")

    files = result.get("files", {})
    print("-" * 80)
    print("[FILES]")
    for key, value in files.items():
        print(f"{key}: {value}")

    if result.get("status") == "SYNC_COMPLETED_WITH_ERRORS":
        sys.exit(1)


if __name__ == "__main__":
    main()
