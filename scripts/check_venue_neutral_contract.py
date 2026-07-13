from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src/crypto_ai_system/execution/venue_contracts.py"
EXECUTOR = ROOT / "src/crypto_ai_system/execution/signed_testnet_order_executor.py"


def main() -> int:
    failures: list[str] = []
    for path in (CONTRACT, EXECUTOR):
        text = path.read_text(encoding="utf-8").lower()
        for token in ("/fapi/", "binancefuture.com", "hmac-sha256", "btc" + "usdt"):
            if token in text:
                failures.append(f"VENUE_SPECIFIC_TOKEN_IN_CANONICAL_CORE:{path.relative_to(ROOT)}:{token}")
    contract_text = CONTRACT.read_text(encoding="utf-8")
    for name in (
        "ExternalVenueRuntimePackage",
        "VenueCredentialReference",
        "VenueSignerProtocol",
        "VenueSubmitTransport",
        "VenueOrderIntent",
        "VenueSubmitReceipt",
        "VenueStatusEvent",
        "VenueEvidenceBundle",
    ):
        if name not in contract_text:
            failures.append(f"P70_REQUIRED_CONTRACT_MISSING:{name}")
    if failures:
        print("P70 venue-neutral contract: BLOCKED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("P70 venue-neutral contract: VALID; submit/network remain disabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
