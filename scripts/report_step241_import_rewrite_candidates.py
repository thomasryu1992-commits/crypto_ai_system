from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_legacy_root_import_retirement import build_import_retirement_plan


LOW_RISK_ACTIONS = {
    "READY_FOR_CANONICAL_IMPORT_REWRITE",
    "READY_FOR_PACKAGE_LEVEL_CANONICAL_IMPORT_REWRITE",
}


def build_step241_rewrite_report(root: Path) -> dict:
    plan = build_import_retirement_plan(root)
    low_remaining = [
        row
        for row in plan["rows"]
        if row["risk_level"] == "LOW" and row["suggested_action"] in LOW_RISK_ACTIONS
    ]
    return {
        "report_type": "step241_legacy_root_import_rewrite_candidate_report",
        "status": "LOW_RISK_REWRITE_REVIEW",
        "canonical_package_root": "src/crypto_ai_system",
        "direct_root_import_finding_count": plan["direct_root_import_finding_count"],
        "findings_by_action": plan["findings_by_action"],
        "findings_by_risk": plan["findings_by_risk"],
        "low_risk_rewrite_candidate_remaining_count": len(low_remaining),
        "low_risk_rewrite_candidates_remaining": low_remaining,
        "rewrite_scope": "LOW_RISK_EXACT_CANONICAL_IMPORTS_ONLY",
        "manual_mapping_imports_untouched": plan["findings_by_action"].get("MANUAL_MAPPING_REQUIRED", 0),
        "wrapper_conversion_performed": False,
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "next_step": {
            "name": "Step242 v5 Manual Mapping Review for Legacy Root Imports",
            "goal": "Map the remaining MANUAL_MAPPING_REQUIRED imports to canonical modules before thin wrapper conversion.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step241 post-rewrite candidate report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step241_legacy_root_import_rewrite_candidate_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step241_rewrite_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "low_risk_rewrite_candidate_remaining_count": report["low_risk_rewrite_candidate_remaining_count"],
        "manual_mapping_imports_untouched": report["manual_mapping_imports_untouched"],
        "wrapper_conversion_performed": report["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
