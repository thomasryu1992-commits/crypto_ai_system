from __future__ import annotations

from crypto_ai_system.execution.repeated_clean_signed_testnet_sessions import persist_repeated_clean_signed_testnet_sessions


if __name__ == "__main__":
    report = persist_repeated_clean_signed_testnet_sessions()
    print(report["status"])
    print(report["p8_repeated_clean_signed_testnet_sessions_sha256"])
