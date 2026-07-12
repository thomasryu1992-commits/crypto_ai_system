from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_runtime_authority_bridge import persist_phase9_2_runtime_authority_bridge_report


def main() -> None:
    report = persist_phase9_2_runtime_authority_bridge_report(run_real_submit_gate_first=True)
    print(report["status"])


if __name__ == "__main__":
    main()
