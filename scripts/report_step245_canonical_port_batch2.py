from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_canonical_ports_for_root_only_features import build_canonical_port_plan
from plan_legacy_root_import_retirement import build_import_retirement_plan


BATCH2_PORTED_LEGACY_MODULES = {
    "trading.paper_report": "crypto_ai_system.trading.paper_report",
}


def build_step245_batch2_report(root: Path) -> dict:
    retirement_plan = build_import_retirement_plan(root)
    canonical_port_plan = build_canonical_port_plan(root)

    remaining_legacy_modules = {
        group["legacy_module"]
        for group in canonical_port_plan.get("groups", [])
    }
    ported_remaining = sorted(set(BATCH2_PORTED_LEGACY_MODULES) & remaining_legacy_modules)

    return {
        "report_type": "step245_canonical_port_batch2_report",
        "status": "BATCH2_CANONICAL_PORT_APPLIED",
        "batch_scope": "TRADING_PAPER_REPORT_CANONICAL_PORT",
        "ported_modules": BATCH2_PORTED_LEGACY_MODULES,
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
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "next_step": {
            "name": "Step246 v5 Canonical Port Patch Batch 3",
            "goal": "Port the next isolated HIGH-priority legacy group with tests and limited import rewrite.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step245 canonical port batch 2 report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step245_canonical_port_batch2_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step245_batch2_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "remaining_root_only_input_count": report["remaining_root_only_input_count"],
        "remaining_port_group_count": report["remaining_port_group_count"],
        "ported_modules_still_in_port_plan": report["ported_modules_still_in_port_plan"],
        "expected_ported_modules_removed_from_plan": report["expected_ported_modules_removed_from_plan"],
        "wrapper_conversion_performed": report["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
