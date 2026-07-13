from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_canonical_ports_for_root_only_features import build_canonical_port_plan
from plan_legacy_root_import_retirement import build_import_retirement_plan


BATCH4_PORTED_LEGACY_MODULES = {
    "trading.paper_engine": "crypto_ai_system.trading.paper_engine",
}

BATCH4_SUPPORT_MODULES = {
    "trading.position_sizing": "crypto_ai_system.trading.position_sizing",
}


def build_step247_batch4_report(root: Path) -> dict:
    retirement_plan = build_import_retirement_plan(root)
    canonical_port_plan = build_canonical_port_plan(root)

    remaining_legacy_modules = {
        group["legacy_module"]
        for group in canonical_port_plan.get("groups", [])
    }
    ported_remaining = sorted(set(BATCH4_PORTED_LEGACY_MODULES) & remaining_legacy_modules)

    return {
        "report_type": "step247_canonical_port_batch4_report",
        "status": "BATCH4_CANONICAL_PORT_APPLIED_PAPER_ONLY",
        "batch_scope": "TRADING_PAPER_ENGINE_CANONICAL_PORT",
        "ported_modules": BATCH4_PORTED_LEGACY_MODULES,
        "support_modules_ported": BATCH4_SUPPORT_MODULES,
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
        "paper_engine_mode": "PAPER_ONLY",
        "live_trading_allowed": False,
        "paper_execution_enabled_by_this_step": False,
        "adapter_routing_enabled": False,
        "external_order_submission_performed": False,
        "next_step": {
            "name": "Step248 v5 Medium Priority Canonical Port Batch",
            "goal": "Port the next medium-priority legacy group with tests and limited import rewrite.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step247 canonical port batch 4 report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step247_canonical_port_batch4_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step247_batch4_report(root)
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
        "paper_engine_mode": report["paper_engine_mode"],
        "live_trading_allowed": report["live_trading_allowed"],
        "external_order_submission_performed": report["external_order_submission_performed"],
        "wrapper_conversion_performed": report["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
