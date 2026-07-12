from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

bootstrap()

from crypto_ai_system.validation.phase9_2_real_testnet_endpoint_adapter_preflight import persist_phase9_2_real_testnet_endpoint_adapter_preflight


def main() -> int:
    report = persist_phase9_2_real_testnet_endpoint_adapter_preflight()
    print(json.dumps({
        "status": report["status"],
        "blocked": report["blocked"],
        "fail_closed": report["fail_closed"],
        "preflight_ready_for_manual_review_only": report["preflight_ready_for_manual_review_only"],
        "real_testnet_submit_may_begin": report["real_testnet_submit_may_begin"],
        "order_endpoint_called": report["order_endpoint_called"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
