from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plan_legacy_root_import_retirement import build_import_retirement_plan
from plan_thin_wrapper_conversion import build_thin_wrapper_conversion_plan


DISPOSITION_POLICY: dict[str, dict[str, Any]] = {
    "execution.exchange_router": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "DISABLED_REVIEW_ONLY_ROUTER",
        "priority": "HIGH",
        "risk_level": "HIGH",
        "target_step": "Step255",
        "safety_boundary": "External routing remains disabled unless explicitly approved; no live order submission.",
        "reason": "Routing boundary should become canonical, but must stay disabled/review-only and depend on canonical support modules.",
    },
    "execution.live_executor": {
        "disposition": "KEEP_EXPLICIT_LEGACY_COMPATIBILITY",
        "port_subtype": "DISABLED_LIVE_EXECUTION_STUB",
        "priority": "LOW",
        "risk_level": "HIGH",
        "target_step": "DEFER",
        "safety_boundary": "Live executor remains explicit disabled legacy stub until real live execution architecture is approved.",
        "reason": "The current implementation intentionally raises NotImplementedError; porting it provides little value before live architecture design.",
    },
    "execution.mock_exchange": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "TEST_SUPPORT_ONLY",
        "priority": "HIGH",
        "risk_level": "LOW",
        "target_step": "Step255",
        "safety_boundary": "Mock exchange is local deterministic test support only; no network calls.",
        "reason": "Order router and tests need a canonical deterministic mock exchange client.",
    },
    "execution.order_models": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "ORDER_MODEL_SUPPORT",
        "priority": "HIGH",
        "risk_level": "LOW",
        "target_step": "Step255",
        "safety_boundary": "Pure request construction/validation only; no execution.",
        "reason": "Order request model utilities are pure support code and should be canonical before router cleanup.",
    },
    "execution.order_state": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "ORDER_STATE_SUPPORT",
        "priority": "HIGH",
        "risk_level": "LOW",
        "target_step": "Step255",
        "safety_boundary": "Pure state transition constants/validation only; no execution.",
        "reason": "Order state constants are pure support code and safe to canonicalize with tests.",
    },
    "execution.testnet_executor": {
        "disposition": "KEEP_EXPLICIT_LEGACY_COMPATIBILITY",
        "port_subtype": "DISABLED_TESTNET_EXECUTION_STUB",
        "priority": "MEDIUM",
        "risk_level": "HIGH",
        "target_step": "DEFER",
        "safety_boundary": "Testnet executor remains disabled until signed REST implementation and testnet lifecycle validation exist.",
        "reason": "The module touches future exchange execution; keep explicit disabled compatibility until testnet adapter design is approved.",
    },
    "trading.paper_watch": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "PAPER_ONLY_REPORTING",
        "priority": "MEDIUM",
        "risk_level": "MEDIUM",
        "target_step": "Step256",
        "safety_boundary": "Paper-watch reporting only; no order execution.",
        "reason": "Paper-watch output belongs in canonical trading package but needs settings/storage-path compatibility repair.",
    },
    "research.dynamic_setup_generator": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "RESEARCH_ONLY_LEGACY_V1",
        "priority": "MEDIUM",
        "risk_level": "MEDIUM",
        "target_step": "Step256",
        "safety_boundary": "Research setup generation only; no trading execution.",
        "reason": "Legacy research v1 flow can be canonicalized as report-only after storage-path compatibility repair.",
    },
    "research.research_cycle": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "RESEARCH_ONLY_LEGACY_V1",
        "priority": "MEDIUM",
        "risk_level": "MEDIUM",
        "target_step": "Step256",
        "safety_boundary": "Research report generation only; no trading execution.",
        "reason": "Legacy research cycle can be canonicalized as report-only after storage-path compatibility repair.",
    },
    "research.research_decision": {
        "disposition": "PORT_TO_CANONICAL",
        "port_subtype": "RESEARCH_DECISION_ONLY_LEGACY_V1",
        "priority": "MEDIUM",
        "risk_level": "MEDIUM",
        "target_step": "Step256",
        "safety_boundary": "Research decision generation only; no order routing.",
        "reason": "Legacy decision output can be canonicalized after storage-path compatibility repair.",
    },
}


@dataclass
class MissingCanonicalDispositionRow:
    legacy_module: str
    domain: str
    root_file: str
    proposed_canonical_module: str
    proposed_canonical_file: str
    root_exported_symbols: list[str]
    root_internal_legacy_imports: list[str]
    uses_settings_storage_path: bool
    uses_network_or_exchange_boundary: bool
    current_wrapper_action: str
    disposition: str
    port_subtype: str
    priority: str
    risk_level: str
    target_step: str
    safety_boundary: str
    required_repairs: list[str]
    test_requirements: list[str]
    reason: str


def _legacy_imports_in_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"execution", "trading", "research"}:
                imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"execution", "trading", "research"}:
                    imports.add(alias.name)
    return sorted(imports)


def _required_repairs(path: Path, row: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    repairs: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    legacy_imports = _legacy_imports_in_file(path)
    if legacy_imports:
        repairs.append("rewrite_internal_legacy_imports_to_canonical")
    if "from config.settings import storage_path" in text or "storage_path(" in text:
        repairs.append("replace_or_restore_storage_path_compatibility")
    if policy["disposition"] == "PORT_TO_CANONICAL" and policy["risk_level"] == "HIGH":
        repairs.append("add_disabled_or_review_only_safety_flags")
    if "ENABLE_TESTNET_ORDERS" in text or "LIVE_TRADING_ENABLED" in text or "EXCHANGE_ORDER_ENABLED" in text:
        repairs.append("preserve_execution_disabled_defaults")
    if row.get("root_exported_symbols"):
        repairs.append("add_symbol_compatibility_tests")
    return sorted(set(repairs))


def _test_requirements(policy: dict[str, Any]) -> list[str]:
    base = ["legacy_import_compatibility_test", "canonical_symbol_export_test"]
    if policy["disposition"] == "PORT_TO_CANONICAL":
        base.append("canonical_behavior_equivalence_test")
    if policy["risk_level"] in {"MEDIUM", "HIGH"}:
        base.append("safety_boundary_test")
    if "DISABLED" in policy["port_subtype"] or "EXECUTION" in policy["port_subtype"] or "ROUTER" in policy["port_subtype"]:
        base.append("no_external_order_submission_test")
    return sorted(set(base))


def build_missing_canonical_disposition_plan(root: Path) -> dict[str, Any]:
    import_plan = build_import_retirement_plan(root)
    wrapper_plan = build_thin_wrapper_conversion_plan(root)
    missing_rows = [
        row for row in wrapper_plan["rows"]
        if row["recommended_action"] == "CANONICAL_MODULE_MISSING"
    ]

    rows: list[MissingCanonicalDispositionRow] = []
    for row in missing_rows:
        legacy_module = row["legacy_module"]
        policy = DISPOSITION_POLICY.get(legacy_module)
        if policy is None:
            policy = {
                "disposition": "KEEP_EXPLICIT_LEGACY_COMPATIBILITY",
                "port_subtype": "UNCLASSIFIED_LEGACY_COMPATIBILITY",
                "priority": "LOW",
                "risk_level": "MEDIUM",
                "target_step": "DEFER",
                "safety_boundary": "No automatic port until manually classified.",
                "reason": "No explicit disposition policy exists.",
            }
        root_file = root / row["root_file"]
        text = root_file.read_text(encoding="utf-8", errors="ignore") if root_file.exists() else ""
        rows.append(
            MissingCanonicalDispositionRow(
                legacy_module=legacy_module,
                domain=row["domain"],
                root_file=row["root_file"],
                proposed_canonical_module=row["canonical_module"],
                proposed_canonical_file=row["canonical_file"],
                root_exported_symbols=row.get("root_exported_symbols", []),
                root_internal_legacy_imports=_legacy_imports_in_file(root_file),
                uses_settings_storage_path="storage_path" in text,
                uses_network_or_exchange_boundary=any(
                    token in text
                    for token in [
                        "LIVE_TRADING_ENABLED",
                        "EXCHANGE_ORDER_ENABLED",
                        "ENABLE_TESTNET_ORDERS",
                        "place_order",
                        "route_order",
                        "TestnetExecutor",
                        "LiveExecutor",
                    ]
                ),
                current_wrapper_action=row["recommended_action"],
                disposition=policy["disposition"],
                port_subtype=policy["port_subtype"],
                priority=policy["priority"],
                risk_level=policy["risk_level"],
                target_step=policy["target_step"],
                safety_boundary=policy["safety_boundary"],
                required_repairs=_required_repairs(root_file, row, policy),
                test_requirements=_test_requirements(policy),
                reason=policy["reason"],
            )
        )

    counts: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_target_step: dict[str, int] = {}
    for item in rows:
        counts[item.disposition] = counts.get(item.disposition, 0) + 1
        by_priority[item.priority] = by_priority.get(item.priority, 0) + 1
        by_risk[item.risk_level] = by_risk.get(item.risk_level, 0) + 1
        by_target_step[item.target_step] = by_target_step.get(item.target_step, 0) + 1

    return {
        "plan_type": "missing_canonical_module_disposition_plan",
        "status": "PLAN_ONLY_NO_PORT_OR_DELETE",
        "direct_root_import_finding_count": import_plan["direct_root_import_finding_count"],
        "root_direct_imports_retired": import_plan["direct_root_import_finding_count"] == 0,
        "missing_canonical_module_count": len(rows),
        "disposition_counts": dict(sorted(counts.items())),
        "priority_counts": dict(sorted(by_priority.items())),
        "risk_counts": dict(sorted(by_risk.items())),
        "target_step_counts": dict(sorted(by_target_step.items())),
        "port_to_canonical_count": counts.get("PORT_TO_CANONICAL", 0),
        "keep_explicit_legacy_compatibility_count": counts.get("KEEP_EXPLICIT_LEGACY_COMPATIBILITY", 0),
        "retire_or_deprecate_count": counts.get("RETIRE_OR_DEPRECATE", 0),
        "port_performed": False,
        "wrapper_conversion_performed": False,
        "root_package_deletion_performed": False,
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "external_order_submission_performed": False,
        "rows": [asdict(row) for row in rows],
        "recommended_sequence": [
            "Step255: port low-risk/high-priority execution support modules first: order_models, order_state, mock_exchange.",
            "Step256: port paper/research legacy v1 reporting modules after storage_path compatibility repair.",
            "Keep live_executor and testnet_executor as explicit disabled legacy compatibility until live/testnet architecture is designed.",
            "Only revisit root package deletion after all remaining modules are ported, retired, or explicitly documented as compatibility surfaces.",
        ],
        "next_step": {
            "name": "Step255 v5 Execution Support Canonical Port Batch",
            "goal": "Port execution.order_models, execution.order_state, and execution.mock_exchange with tests and no execution enablement.",
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "legacy_module",
        "domain",
        "root_file",
        "proposed_canonical_module",
        "disposition",
        "port_subtype",
        "priority",
        "risk_level",
        "target_step",
        "required_repairs",
        "test_requirements",
        "safety_boundary",
        "reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["required_repairs"] = "|".join(out.get("required_repairs", []))
            out["test_requirements"] = "|".join(out.get("test_requirements", []))
            writer.writerow({field: out.get(field, "") for field in fields})


def _write_markdown(path: Path, plan: dict[str, Any]) -> None:
    lines = [
        "# Step254 Missing Canonical Module Disposition Plan",
        "",
        "Step254 classifies remaining `CANONICAL_MODULE_MISSING` root modules.",
        "",
        "No modules are ported, deleted, or converted in Step254.",
        "",
        "## Summary",
        "",
        f"- status: `{plan['status']}`",
        f"- direct root import finding count: `{plan['direct_root_import_finding_count']}`",
        f"- missing canonical module count: `{plan['missing_canonical_module_count']}`",
        f"- port to canonical: `{plan['port_to_canonical_count']}`",
        f"- keep explicit legacy compatibility: `{plan['keep_explicit_legacy_compatibility_count']}`",
        f"- retire/deprecate: `{plan['retire_or_deprecate_count']}`",
        "",
        "## Disposition Counts",
        "",
    ]
    for key, value in plan["disposition_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Rows", ""])
    for row in plan["rows"]:
        lines.append(
            f"- `{row['legacy_module']}` disposition=`{row['disposition']}` "
            f"subtype=`{row['port_subtype']}` priority=`{row['priority']}` risk=`{row['risk_level']}`"
        )
    lines.extend(["", "## Recommended Sequence", ""])
    for item in plan["recommended_sequence"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Safety Boundary",
        "",
        "Step254 does not enable paper execution, order execution, adapter routing, external API calls, Telegram real sends, or live trading.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan disposition for missing canonical root modules.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-output", default="data/reports/step254_missing_canonical_disposition_plan.json")
    parser.add_argument("--csv-output", default="data/reports/step254_missing_canonical_disposition_plan.csv")
    parser.add_argument("--md-output", default="data/reports/step254_missing_canonical_disposition_plan.md")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan = build_missing_canonical_disposition_plan(root)

    json_path = Path(args.json_output)
    csv_path = Path(args.csv_output)
    md_path = Path(args.md_output)
    if not json_path.is_absolute():
        json_path = root / json_path
    if not csv_path.is_absolute():
        csv_path = root / csv_path
    if not md_path.is_absolute():
        md_path = root / md_path

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    _write_csv(csv_path, plan["rows"])
    _write_markdown(md_path, plan)

    print(json.dumps({
        "status": plan["status"],
        "json_output": str(json_path),
        "csv_output": str(csv_path),
        "md_output": str(md_path),
        "direct_root_import_finding_count": plan["direct_root_import_finding_count"],
        "missing_canonical_module_count": plan["missing_canonical_module_count"],
        "disposition_counts": plan["disposition_counts"],
        "priority_counts": plan["priority_counts"],
        "risk_counts": plan["risk_counts"],
        "port_performed": plan["port_performed"],
        "wrapper_conversion_performed": plan["wrapper_conversion_performed"],
        "root_package_deletion_performed": plan["root_package_deletion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
