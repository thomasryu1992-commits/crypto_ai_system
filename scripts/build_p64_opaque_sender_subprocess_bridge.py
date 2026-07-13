from __future__ import annotations

from crypto_ai_system.execution.opaque_sender_subprocess_bridge import (
    persist_p64_opaque_sender_subprocess_bridge,
)

if __name__ == "__main__":
    report = persist_p64_opaque_sender_subprocess_bridge()
    print(report["status"])
    print(report["p64_opaque_sender_subprocess_bridge_sha256"])
