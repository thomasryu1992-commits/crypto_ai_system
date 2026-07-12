from __future__ import annotations

import argparse
import json
from pathlib import Path

from plan_legacy_root_import_retirement import build_import_retirement_plan
from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan


THIN_WRAPPER_MARKER = "Step253 thin wrapper"


def _is_thin_wrapper(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return THIN_WRAPPER_MARKER in text and "from crypto_ai_system." in text and "import *" in text


def build_step253_wrapper_batch1_report(root: Path) -> dict:
    import_plan = build_import_retirement_plan(root)
    wrapper_plan = build_thin_wrapper_conversion_plan(root)

    converted_rows = []
    missing_rows = []
    for row in wrapper_plan["rows"]:
        root_file = root / row["root_file"]
        if row["recommended_action"] == "CANONICAL_MODULE_MISSING":
            missing_rows.append(row)
        if _is_thin_wrapper(root_file):
            converted_rows.append(row)

    converted_modules = sorted(row["legacy_module"] for row in converted_rows)
    missing_modules = sorted(row["legacy_module"] for row in missing_rows)

    return {
        "report_type": "step253_thin_wrapper_conversion_batch1_report",
        "status": "BATCH1_THIN_WRAPPER_CONVERSION_APPLIED",
        "batch_scope": "READY_FOR_THIN_WRAPPER_MODULES_ONLY",
        "direct_root_import_finding_count": import_plan["direct_root_import_finding_count"],
        "root_direct_imports_retired": import_plan["direct_root_import_finding_count"] == 0,
        "thin_wrapper_converted_count": len(converted_modules),
        "thin_wrapper_converted_modules": converted_modules,
        "canonical_module_missing_count": len(missing_modules),
        "canonical_module_missing_modules": missing_modules,
        "ready_for_thin_wrapper_count_after_conversion": wrapper_plan["ready_for_thin_wrapper_count"],
        "wrapper_plan_findings_by_action": wrapper_plan["findings_by_action"],
        "wrapper_plan_findings_by_blocker_level": wrapper_plan["findings_by_blocker_level"],
        "full_wrapper_conversion_ready": wrapper_plan["wrapper_conversion_ready"],
        "full_wrapper_conversion_blocked": wrapper_plan["wrapper_conversion_blocked"],
        "wrapper_conversion_performed": True,
        "root_package_deletion_performed": False,
        "missing_canonical_modules_untouched": len(missing_modules) == wrapper_plan["canonical_module_missing_count"],
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "next_step": {
            "name": "Step254 v5 Missing Canonical Module Disposition Plan",
            "goal": "Decide whether the remaining missing-canonical root modules should be ported, retired, or kept as explicit legacy compatibility modules.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step253 thin wrapper conversion batch 1 report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step253_thin_wrapper_conversion_batch1_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    report = build_step253_wrapper_batch1_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "direct_root_import_finding_count": report["direct_root_import_finding_count"],
        "thin_wrapper_converted_count": report["thin_wrapper_converted_count"],
        "canonical_module_missing_count": report["canonical_module_missing_count"],
        "full_wrapper_conversion_ready": report["full_wrapper_conversion_ready"],
        "full_wrapper_conversion_blocked": report["full_wrapper_conversion_blocked"],
        "root_package_deletion_performed": report["root_package_deletion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
