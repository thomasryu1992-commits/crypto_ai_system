from __future__ import annotations

from execution.execution_reconciler import run_execution_reconciliation


def main() -> None:
    result = run_execution_reconciliation("storage")
    print("[EXECUTION RECONCILIATION TEST]")
    print(f"Status: {result.get('status')}")
    print(f"Reconciled: {result.get('reconciled')}")
    print("[CHECKS]")
    for check in result.get("checks", []):
        print(f"- {check.get('name')}: {check.get('passed')} / {check.get('message')}")


if __name__ == "__main__":
    main()
