from __future__ import annotations

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.repeated_clean_live_canary_sessions import persist_repeated_clean_live_canary_sessions


def main() -> int:
    report = persist_repeated_clean_live_canary_sessions(cfg=load_config())
    print(report["status"])
    print(report["p12_repeated_clean_live_canary_sessions_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
