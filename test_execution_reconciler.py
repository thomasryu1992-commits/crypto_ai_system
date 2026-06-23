from __future__ import annotations

from execution.reconciler import reconcile_execution_state


def test_reconcile_execution_state() -> None:
    assert reconcile_execution_state()["status"] == "NO_LIVE_EXECUTION"


if __name__ == "__main__":
    test_reconcile_execution_state()
    print("PASSED")
