from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_blocked_executor_wrapper import persist_phase9_2_blocked_executor_wrapper_report
from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import persist_phase9_3_status_polling_cancel_handling_report


def main() -> None:
    p92 = persist_phase9_2_blocked_executor_wrapper_report(run_submit_guard_recheck_first=True)
    p93 = persist_phase9_3_status_polling_cancel_handling_report(run_phase9_2_blocked_wrapper_first=False)
    print(p92["status"])
    print(p93["status"])


if __name__ == "__main__":
    main()
