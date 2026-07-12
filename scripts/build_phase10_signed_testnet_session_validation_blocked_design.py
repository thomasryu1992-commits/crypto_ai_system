from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase10_signed_testnet_session_validation_blocked_design import (
    persist_phase10_signed_testnet_session_validation_blocked_design_report,
)


def main() -> None:
    report = persist_phase10_signed_testnet_session_validation_blocked_design_report(run_phase9_3_9_4_first=True)
    print(report["status"])


if __name__ == "__main__":
    main()
