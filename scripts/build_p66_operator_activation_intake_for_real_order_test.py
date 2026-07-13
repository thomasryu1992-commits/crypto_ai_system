from __future__ import annotations

from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from crypto_ai_system.execution.operator_activation_intake_for_real_order_test import (
    persist_p66_operator_activation_intake_for_real_order_test,
)


if __name__ == "__main__":
    report = persist_p66_operator_activation_intake_for_real_order_test(Path.cwd())
    print(report["status"])
