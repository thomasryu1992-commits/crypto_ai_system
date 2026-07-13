from __future__ import annotations
from pathlib import Path
from crypto_ai_system.execution.operator_installed_testnet_sender_executable import persist_p65_operator_installed_testnet_sender_executable

if __name__ == "__main__":
    report = persist_p65_operator_installed_testnet_sender_executable(Path.cwd())
    print(report["status"])
