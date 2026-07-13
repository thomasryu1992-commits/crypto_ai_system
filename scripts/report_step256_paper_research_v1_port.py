from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_legacy_root_import_retirement import build_import_retirement_plan
from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan
from plan_missing_canonical_module_disposition import build_missing_canonical_disposition_plan


PORTED_MODULES = {
    "trading.paper_watch": "crypto_ai_system.trading.paper_watch",
    "research.dynamic_setup_generator": "crypto_ai_system.research.dynamic_setup_generator",
    "research.research_cycle": "crypto_ai_system.research.research_cycle",
    "research.research_decision": "crypto_ai_system.research.research_decision",
}


def _has_step256_wrapper(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "Step256 thin compatibility wrapper" in text and "from crypto_ai_system." in text and "import *" in text


def build_step256_paper_research_report(root: Path) -> dict:
    import_plan = build_import_retirement_plan(root)
    wrapper_plan = build_thin_wrapper_conversion_plan(root)
    disposition_plan = build_missing_canonical_disposition_plan(root)

    wrappers = []
    for legacy_module in PORTED_MODULES:
        root_file = (root / legacy_module.replace(".", "/")).with_suffix(".py")
        if _has_step256_wrapper(root_file):
            wrappers.append(legacy_module)

    return {
        "report_type": "step256_paper_research_v1_canonical_port_report",
        "status": "PAPER_RESEARCH_LEGACY_V1_CANONICAL_PORT_APPLIED",
        "ported_modules": PORTED_MODULES,
        "step256_wrapper_modules": sorted(wrappers),
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
        "paper_watch_mode": "PAPER_REPORT_ONLY",
        "dynamic_setup_mode": "RESEARCH_ONLY_LEGACY_V1",
        "research_cycle_mode": "RESEARCH_REPORT_ONLY_LEGACY_V1",
        "research_decision_mode": "RESEARCH_DECISION_ONLY_LEGACY_V1",
        "trading_execution_enabled": False,
        "order_routing_enabled": False,
        "external_order_submission_performed": False,
        "deferred_modules": ["execution.live_executor", "execution.testnet_executor"],
        "next_step": {
            "name": "Step257 v5 Deferred Execution Stub Policy",
            "goal": "Document and harden explicit disabled compatibility for live_executor and testnet_executor without enabling execution.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step256 paper/research legacy v1 canonical port report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step256_paper_research_v1_canonical_port_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step256_paper_research_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "missing_canonical_module_count_after": report["missing_canonical_module_count_after"],
        "ready_for_thin_wrapper_count_after": report["ready_for_thin_wrapper_count_after"],
        "step256_wrapper_module_count": len(report["step256_wrapper_modules"]),
        "trading_execution_enabled": report["trading_execution_enabled"],
        "order_routing_enabled": report["order_routing_enabled"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
