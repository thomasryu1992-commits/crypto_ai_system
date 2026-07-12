from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.ops.operator_dashboard_status import persist_operator_dashboard_status


def main() -> None:
    report = persist_operator_dashboard_status(ROOT)
    print(report["artifact_type"])
    print("execution_flags_all_disabled=", report["execution_flags_all_disabled"])
    print("operator_dashboard_status_sha256=", report["operator_dashboard_status_sha256"])


if __name__ == "__main__":
    main()
