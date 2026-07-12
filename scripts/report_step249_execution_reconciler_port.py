from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_canonical_ports_for_root_only_features import build_canonical_port_plan
from plan_legacy_root_import_retirement import build_import_retirement_plan


BATCH6_PORTED_LEGACY_MODULES = {
    "execution.reconciler": "crypto_ai_system.execution.reconciler",
    "execution.execution_reconciler": "crypto_ai_system.execution.execution_reconciler",
}


def build_step249_batch6_report(root: Path) -> dict:
    retirement_plan = build_import_retirement_plan(root)
    canonical_port_plan = build_canonical_port_plan(root)
    remaining_legacy_modules = {
        group["legacy_module"]
        for group in canonical_port_plan.get("groups", [])
    }
    ported_remaining = sorted(set(BATCH6_PORTED_LEGACY_MODULES) & remaining_legacy_modules)

    return {
        "report_type": "step249_execution_reconciler_canonical_port_report",
        "status": "BATCH6_CANONICAL_PORT_APPLIED_CHECK_ONLY",
        "batch_scope": "EXECUTION_RECONCILER_CHECK_ONLY_CANONICAL_PORT",
        "ported_modules": BATCH6_PORTED_LEGACY_MODULES,
        "ported_modules_still_in_port_plan": ported_remaining,
        "expected_ported_modules_removed_from_plan": len(ported_remaining) == 0,
        "direct_root_import_finding_count": retirement_plan["direct_root_import_finding_count"],
        "findings_by_action": retirement_plan["findings_by_action"],
        "findings_by_risk": retirement_plan["findings_by_risk"],
        "remaining_port_group_count": canonical_port_plan["port_group_count"],
        "remaining_root_only_input_count": canonical_port_plan["root_only_input_count"],
        "remaining_groups_by_priority": canonical_port_plan["groups_by_priority"],
        "remaining_groups_by_domain": canonical_port_plan["groups_by_domain"],
        "port_performed": True,
        "import_rewrite_performed": True,
        "wrapper_conversion_performed": False,
        "wrapper_conversion_blocked": canonical_port_plan["wrapper_conversion_blocked"],
        "reconciler_mode": "CHECK_ONLY",
        "live_position_sync_enabled": False,
        "external_execution_sync_performed": False,
        "live_trading_allowed": False,
        "adapter_routing_enabled": False,
        "next_step": {
            "name": "Step250 v5 Research Engine Canonical Port Batch",
            "goal": "Port research.research_engine and research.decision_engine with tests and limited import rewrite.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step249 execution reconciler canonical port report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step249_execution_reconciler_canonical_port_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step249_batch6_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "remaining_root_only_input_count": report["remaining_root_only_input_count"],
        "remaining_port_group_count": report["remaining_port_group_count"],
        "remaining_groups_by_priority": report["remaining_groups_by_priority"],
        "ported_modules_still_in_port_plan": report["ported_modules_still_in_port_plan"],
        "expected_ported_modules_removed_from_plan": report["expected_ported_modules_removed_from_plan"],
        "reconciler_mode": report["reconciler_mode"],
        "live_position_sync_enabled": report["live_position_sync_enabled"],
        "external_execution_sync_performed": report["external_execution_sync_performed"],
        "wrapper_conversion_performed": report["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
