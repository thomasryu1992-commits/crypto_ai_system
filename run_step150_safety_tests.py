from __future__ import annotations

import importlib
import traceback

from config.settings import LATEST_DIR
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso

TESTS = [
    ("tests.test_step150_safety", "test_spreadsheet_row_has_row_id"),
    ("tests.test_step150_safety", "test_atr_stop_has_min_max_guard"),
    ("tests.test_step150_safety", "test_idempotency_client_order_id_is_stable"),
    ("tests.test_step150_safety", "test_retry_policy_timeout_unknown"),
    ("tests.test_step150_safety", "test_retry_policy_429_unknown_no_immediate_retry"),
    ("tests.test_step150_safety", "test_conservative_paper_engine_sl_first_for_long"),
]


def main() -> None:
    results = []
    passed = 0
    for module_name, fn_name in TESTS:
        try:
            module = importlib.import_module(module_name)
            getattr(module, fn_name)()
            results.append({"test": f"{module_name}.{fn_name}", "status": "PASSED"})
            passed += 1
        except Exception as exc:
            results.append({
                "test": f"{module_name}.{fn_name}",
                "status": "FAILED",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            })

    out = {
        "created_at": utc_now_iso(),
        "status": "PASSED" if passed == len(TESTS) else "FAILED",
        "passed": passed,
        "total": len(TESTS),
        "results": results,
    }
    atomic_write_json(LATEST_DIR / "step150_safety_test_result.json", out)
    print(f"Step150 safety tests: {out['status']} {passed}/{len(TESTS)}")
    if out["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
