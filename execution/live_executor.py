from __future__ import annotations


class LiveExecutor:
    """Real live execution is intentionally disabled in Step150."""

    def place_order(self, intent: dict) -> dict:
        raise NotImplementedError(
            "Real live execution is disabled before real data, paper forward test, testnet execution, reconciliation, and live unlock."
        )
