from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from review_legacy_root_manual_mappings import build_manual_mapping_review


@dataclass
class PortPlanGroup:
    port_group_id: str
    legacy_module: str
    domain: str
    proposed_canonical_module: str
    proposed_canonical_file: str
    root_module_file: str
    root_module_exists: bool
    canonical_exact_module_exists: bool
    import_reference_count: int
    source_files: list[str]
    imported_symbols: list[str]
    root_exported_symbols: list[str]
    symbols_required_by_imports: list[str]
    symbols_missing_from_canonical_domain: list[str]
    port_required_symbols: list[str]
    proposed_port_action: str
    priority: str
    risk_level: str
    test_impact_files: list[str]
    wrapper_conversion_blocker: bool
    reason: str


def _module_path(root: Path, module_name: str) -> tuple[Path, Path]:
    parts = module_name.split(".")
    return root / Path(*parts).with_suffix(".py"), root / Path(*parts) / "__init__.py"


def _canonical_path(root: Path, canonical_module: str) -> tuple[Path, Path]:
    parts = canonical_module.split(".")
    if parts and parts[0] == "crypto_ai_system":
        parts = parts[1:]
    return root / "src" / "crypto_ai_system" / Path(*parts).with_suffix(".py"), root / "src" / "crypto_ai_system" / Path(*parts) / "__init__.py"


def _read_text(py_path: Path, pkg_path: Path) -> str:
    if py_path.exists():
        return py_path.read_text(encoding="utf-8", errors="ignore")
    if pkg_path.exists():
        return pkg_path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _exported_symbols(text: str) -> list[str]:
    if not text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    symbols.add(target.id)
    return sorted(symbols)


def _priority(reference_count: int, symbol_count: int, has_tests: bool) -> str:
    if has_tests or reference_count >= 5:
        return "HIGH"
    if reference_count >= 2 or symbol_count >= 2:
        return "MEDIUM"
    return "LOW"


def _group_rows(review: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in review.get("rows", []):
        if row.get("recommended_action") != "ROOT_ONLY_FEATURE_PORT_REQUIRED":
            continue
        grouped.setdefault(row["legacy_module"], []).append(row)
    return grouped


def build_canonical_port_plan(root: Path) -> dict[str, Any]:
    review = build_manual_mapping_review(root)
    grouped = _group_rows(review)
    groups: list[PortPlanGroup] = []

    for idx, (legacy_module, rows) in enumerate(sorted(grouped.items()), start=1):
        domain = rows[0]["domain"]
        canonical_module = f"crypto_ai_system.{legacy_module}"
        root_py, root_pkg = _module_path(root, legacy_module)
        can_py, can_pkg = _canonical_path(root, canonical_module)
        root_text = _read_text(root_py, root_pkg)
        can_text = _read_text(can_py, can_pkg)

        imported_symbols = sorted(
            {
                symbol
                for row in rows
                for symbol in row.get("imported_symbols", [])
                if symbol
            }
        )
        root_symbols = _exported_symbols(root_text)
        canonical_symbols = _exported_symbols(can_text)
        port_required = sorted([symbol for symbol in imported_symbols if symbol not in canonical_symbols])
        source_files = sorted({row["file"] for row in rows})
        test_impact_files = sorted([f for f in source_files if f.startswith("tests/")])
        priority = _priority(len(rows), len(port_required), bool(test_impact_files))

        if can_py.exists() or can_pkg.exists():
            action = "EXTEND_EXISTING_CANONICAL_MODULE"
            canonical_file = can_py if can_py.exists() else can_pkg
            reason = "Canonical module exists but does not export required legacy symbols."
        else:
            action = "CREATE_CANONICAL_MODULE_FROM_ROOT_LEGACY"
            canonical_file = can_py
            reason = "Exact canonical module is missing; port root legacy functionality into src/crypto_ai_system."

        groups.append(
            PortPlanGroup(
                port_group_id=f"port_group_{idx:03d}",
                legacy_module=legacy_module,
                domain=domain,
                proposed_canonical_module=canonical_module,
                proposed_canonical_file=canonical_file.relative_to(root).as_posix(),
                root_module_file=(root_py if root_py.exists() else root_pkg).relative_to(root).as_posix() if (root_py.exists() or root_pkg.exists()) else "",
                root_module_exists=bool(root_text),
                canonical_exact_module_exists=bool(can_text),
                import_reference_count=len(rows),
                source_files=source_files,
                imported_symbols=imported_symbols,
                root_exported_symbols=root_symbols,
                symbols_required_by_imports=imported_symbols,
                symbols_missing_from_canonical_domain=sorted(
                    {
                        symbol
                        for row in rows
                        for symbol in row.get("missing_from_canonical_domain_symbols", [])
                    }
                ),
                port_required_symbols=port_required,
                proposed_port_action=action,
                priority=priority,
                risk_level="HIGH",
                test_impact_files=test_impact_files,
                wrapper_conversion_blocker=True,
                reason=reason,
            )
        )

    by_action: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for group in groups:
        by_action[group.proposed_port_action] = by_action.get(group.proposed_port_action, 0) + 1
        by_priority[group.priority] = by_priority.get(group.priority, 0) + 1
        by_domain[group.domain] = by_domain.get(group.domain, 0) + 1

    total_required_symbols = sum(len(group.port_required_symbols) for group in groups)
    total_import_refs = sum(group.import_reference_count for group in groups)

    return {
        "plan_type": "canonical_port_plan_for_root_only_legacy_features",
        "status": "PLAN_ONLY_NO_CODE_PORT",
        "canonical_package_root": "src/crypto_ai_system",
        "root_only_input_count": review["findings_by_recommended_action"].get("ROOT_ONLY_FEATURE_PORT_REQUIRED", 0),
        "port_group_count": len(groups),
        "total_import_reference_count": total_import_refs,
        "total_required_symbol_count": total_required_symbols,
        "groups_by_action": dict(sorted(by_action.items())),
        "groups_by_priority": dict(sorted(by_priority.items())),
        "groups_by_domain": dict(sorted(by_domain.items())),
        "port_performed": False,
        "import_rewrite_performed": False,
        "wrapper_conversion_performed": False,
        "wrapper_conversion_blocked": bool(groups),
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "groups": [asdict(group) for group in groups],
        "recommended_sequence": [
            "Port HIGH priority canonical modules first.",
            "Add targeted tests for each canonical port group before import rewrites.",
            "Rewrite imports only after canonical module exports are verified.",
            "Re-run legacy root import retirement plan after each port group.",
            "Convert root packages to thin wrappers only when direct root import count is zero or explicitly approved.",
        ],
        "next_step": {
            "name": "Step244 v5 Canonical Port Patch Batch 1",
            "goal": "Implement the first small batch of HIGH-priority canonical ports with tests.",
        },
    }


def _write_csv(path: Path, groups: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "port_group_id",
        "legacy_module",
        "domain",
        "proposed_canonical_module",
        "proposed_canonical_file",
        "root_module_file",
        "root_module_exists",
        "canonical_exact_module_exists",
        "import_reference_count",
        "imported_symbols",
        "port_required_symbols",
        "proposed_port_action",
        "priority",
        "risk_level",
        "test_impact_files",
        "wrapper_conversion_blocker",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for group in groups:
            out = dict(group)
            for key in ("imported_symbols", "port_required_symbols", "test_impact_files"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow({field: out.get(field, "") for field in fields})


def _write_markdown(path: Path, plan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step243 Canonical Port Plan for Root-Only Legacy Features",
        "",
        "Step243 groups the remaining root-only legacy features into canonical port groups.",
        "",
        "No code is ported, no imports are rewritten, and no wrapper conversion is performed in Step243.",
        "",
        "## Summary",
        "",
        f"- status: `{plan['status']}`",
        f"- root-only input count: `{plan['root_only_input_count']}`",
        f"- port group count: `{plan['port_group_count']}`",
        f"- total import references: `{plan['total_import_reference_count']}`",
        f"- total required symbols: `{plan['total_required_symbol_count']}`",
        f"- wrapper conversion blocked: `{plan['wrapper_conversion_blocked']}`",
        "",
        "## Groups by action",
        "",
    ]
    for action, count in plan["groups_by_action"].items():
        lines.append(f"- `{action}`: {count}")
    lines.extend(["", "## Groups by priority", ""])
    for priority, count in plan["groups_by_priority"].items():
        lines.append(f"- `{priority}`: {count}")
    lines.extend(["", "## Port groups", ""])
    for group in plan["groups"]:
        lines.append(
            f"- `{group['port_group_id']}` `{group['legacy_module']}` → "
            f"`{group['proposed_canonical_module']}` "
            f"action=`{group['proposed_port_action']}` priority=`{group['priority']}` "
            f"refs={group['import_reference_count']} symbols={len(group['port_required_symbols'])}"
        )
    lines.extend(["", "## Recommended sequence", ""])
    for item in plan["recommended_sequence"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Next step",
        "",
        f"- `{plan['next_step']['name']}`",
        f"- Goal: {plan['next_step']['goal']}",
        "",
        "## Safety boundary",
        "",
        "Step243 does not enable paper execution, adapter routing, external API calls, Telegram real sends, or live trading.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a canonical port plan for root-only legacy features.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-output", default="data/reports/step243_canonical_port_plan.json")
    parser.add_argument("--csv-output", default="data/reports/step243_canonical_port_plan.csv")
    parser.add_argument("--md-output", default="data/reports/step243_canonical_port_plan.md")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan = build_canonical_port_plan(root)

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
    _write_csv(csv_path, plan["groups"])
    _write_markdown(md_path, plan)

    print(json.dumps({
        "status": plan["status"],
        "json_output": str(json_path),
        "csv_output": str(csv_path),
        "md_output": str(md_path),
        "root_only_input_count": plan["root_only_input_count"],
        "port_group_count": plan["port_group_count"],
        "total_import_reference_count": plan["total_import_reference_count"],
        "groups_by_action": plan["groups_by_action"],
        "groups_by_priority": plan["groups_by_priority"],
        "wrapper_conversion_blocked": plan["wrapper_conversion_blocked"],
        "port_performed": plan["port_performed"],
        "import_rewrite_performed": plan["import_rewrite_performed"],
        "wrapper_conversion_performed": plan["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
