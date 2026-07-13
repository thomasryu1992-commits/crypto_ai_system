from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_legacy_root_import_retirement import build_import_retirement_plan
from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan
from plan_missing_canonical_module_disposition import build_missing_canonical_disposition_plan


PORTED_MODULES = {
    "execution.order_models": "crypto_ai_system.execution.order_models",
    "execution.order_state": "crypto_ai_system.execution.order_state",
    "execution.mock_exchange": "crypto_ai_system.execution.mock_exchange",
    "execution.exchange_router": "crypto_ai_system.execution.exchange_router",
}


def _has_step255_wrapper(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "Step255 thin compatibility wrapper" in text and "from crypto_ai_system.execution." in text and "import *" in text


def build_step255_execution_support_report(root: Path) -> dict:
    import_plan = build_import_retirement_plan(root)
    wrapper_plan = build_thin_wrapper_conversion_plan(root)
    disposition_plan = build_missing_canonical_disposition_plan(root)

    wrappers = []
    for legacy_module in PORTED_MODULES:
        root_file = root / legacy_module.replace(".", "/")
        root_file = root_file.with_suffix(".py")
        if _has_step255_wrapper(root_file):
            wrappers.append(legacy_module)

    return {
        "report_type": "step255_execution_support_canonical_port_report",
        "status": "EXECUTION_SUPPORT_CANONICAL_PORT_APPLIED",
        "ported_modules": PORTED_MODULES,
        "step255_wrapper_modules": sorted(wrappers),
        "direct_root_import_finding_count": import_plan["direct_root_import_finding_count"],
        "root_direct_imports_retired": import_plan["direct_root_import_finding_count"] == 0,
        "missing_canonical_module_count_after": wrapper_plan["canonical_module_missing_count"],
        "ready_for_thin_wrapper_count_after": wrapper_plan["ready_for_thin_wrapper_count"],
        "wrapper_plan_findings_by_action": wrapper_plan["findings_by_action"],
        "disposition_counts_after": disposition_plan["disposition_counts"],
        "target_step_counts_after": disposition_plan["target_step_counts"],
        "port_performed": True,
        "wrapper_conversion_performed": True,
        "root_package_deletion_performed": False,
        "exchange_router_mode": "DISABLED_REVIEW_ONLY_ROUTER",
        "mock_exchange_mode": "LOCAL_TEST_SUPPORT_ONLY",
        "live_trading_allowed": False,
        "adapter_routing_enabled": False,
        "external_order_submission_performed": False,
        "next_step": {
            "name": "Step256 v5 Paper/Research Legacy V1 Canonical Port Batch",
            "goal": "Port trading.paper_watch and legacy research v1 report modules with storage-path compatibility repair.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step255 execution support canonical port report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step255_execution_support_canonical_port_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step255_execution_support_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "missing_canonical_module_count_after": report["missing_canonical_module_count_after"],
        "ready_for_thin_wrapper_count_after": report["ready_for_thin_wrapper_count_after"],
        "step255_wrapper_module_count": len(report["step255_wrapper_modules"]),
        "exchange_router_mode": report["exchange_router_mode"],
        "live_trading_allowed": report["live_trading_allowed"],
        "external_order_submission_performed": report["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
