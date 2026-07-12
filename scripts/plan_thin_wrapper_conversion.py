from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plan_legacy_root_import_retirement import build_import_retirement_plan


DOMAINS = ("execution", "trading", "research")


@dataclass
class WrapperPlanRow:
    domain: str
    root_module: str
    legacy_module: str
    canonical_module: str
    root_file: str
    canonical_file: str
    root_module_exists: bool
    canonical_module_exists: bool
    root_exported_symbols: list[str]
    canonical_exported_symbols: list[str]
    missing_canonical_symbols: list[str]
    extra_canonical_symbols: list[str]
    recommended_action: str
    blocker_level: str
    reason: str


def _exported_symbols(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
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


def _module_names(base: Path) -> list[str]:
    if not base.exists():
        return []
    return sorted(
        [
            p.relative_to(base).with_suffix("").as_posix().replace("/", ".")
            for p in base.rglob("*.py")
            if p.name != "__init__.py"
        ]
    )


def _file_for_module(base: Path, module_name: str) -> Path:
    return base / Path(*module_name.split(".")).with_suffix(".py")


def _classify(root: Path, domain: str, module_name: str) -> WrapperPlanRow:
    root_base = root / domain
    canonical_base = root / "src" / "crypto_ai_system" / domain

    root_file = _file_for_module(root_base, module_name)
    canonical_file = _file_for_module(canonical_base, module_name)

    root_exports = _exported_symbols(root_file)
    canonical_exports = _exported_symbols(canonical_file)
    missing = sorted(set(root_exports) - set(canonical_exports))
    extra = sorted(set(canonical_exports) - set(root_exports))

    legacy_module = f"{domain}.{module_name}"
    canonical_module = f"crypto_ai_system.{domain}.{module_name}"

    if canonical_file.exists() and not missing:
        action = "READY_FOR_THIN_WRAPPER"
        blocker = "LOW"
        reason = "Exact canonical module exists and exports all root public symbols."
    elif canonical_file.exists() and missing:
        action = "CANONICAL_EXPORT_REPAIR_REQUIRED"
        blocker = "MEDIUM"
        reason = "Exact canonical module exists but is missing public symbols expected from the root module."
    else:
        action = "CANONICAL_MODULE_MISSING"
        blocker = "HIGH"
        reason = "Root module does not have an exact canonical module; port, retire, or document external compatibility before wrapper conversion."

    return WrapperPlanRow(
        domain=domain,
        root_module=module_name,
        legacy_module=legacy_module,
        canonical_module=canonical_module,
        root_file=root_file.relative_to(root).as_posix(),
        canonical_file=canonical_file.relative_to(root).as_posix(),
        root_module_exists=root_file.exists(),
        canonical_module_exists=canonical_file.exists(),
        root_exported_symbols=root_exports,
        canonical_exported_symbols=canonical_exports,
        missing_canonical_symbols=missing,
        extra_canonical_symbols=extra,
        recommended_action=action,
        blocker_level=blocker,
        reason=reason,
    )


def build_thin_wrapper_conversion_plan(root: Path) -> dict[str, Any]:
    import_plan = build_import_retirement_plan(root)

    rows: list[WrapperPlanRow] = []
    domain_summary: dict[str, dict[str, Any]] = {}
    for domain in DOMAINS:
        root_base = root / domain
        canonical_base = root / "src" / "crypto_ai_system" / domain
        root_modules = _module_names(root_base)
        canonical_modules = _module_names(canonical_base)

        for module_name in root_modules:
            rows.append(_classify(root, domain, module_name))

        ready = [row for row in rows if row.domain == domain and row.recommended_action == "READY_FOR_THIN_WRAPPER"]
        repair = [row for row in rows if row.domain == domain and row.recommended_action == "CANONICAL_EXPORT_REPAIR_REQUIRED"]
        missing = [row for row in rows if row.domain == domain and row.recommended_action == "CANONICAL_MODULE_MISSING"]
        domain_summary[domain] = {
            "root_module_count": len(root_modules),
            "canonical_module_count": len(canonical_modules),
            "ready_for_thin_wrapper_count": len(ready),
            "canonical_export_repair_required_count": len(repair),
            "canonical_module_missing_count": len(missing),
            "root_modules_without_exact_canonical": [row.root_module for row in missing],
        }

    by_action: dict[str, int] = {}
    by_blocker: dict[str, int] = {}
    for row in rows:
        by_action[row.recommended_action] = by_action.get(row.recommended_action, 0) + 1
        by_blocker[row.blocker_level] = by_blocker.get(row.blocker_level, 0) + 1

    direct_root_import_count = int(import_plan.get("direct_root_import_finding_count", 0) or 0)
    blockers = [row for row in rows if row.blocker_level in {"MEDIUM", "HIGH"}]

    return {
        "plan_type": "thin_wrapper_conversion_plan",
        "status": "PLAN_ONLY_NO_WRAPPER_CONVERSION",
        "canonical_package_root": "src/crypto_ai_system",
        "domains": list(DOMAINS),
        "direct_root_import_finding_count": direct_root_import_count,
        "root_direct_imports_retired": direct_root_import_count == 0,
        "root_module_count": len(rows),
        "ready_for_thin_wrapper_count": by_action.get("READY_FOR_THIN_WRAPPER", 0),
        "canonical_export_repair_required_count": by_action.get("CANONICAL_EXPORT_REPAIR_REQUIRED", 0),
        "canonical_module_missing_count": by_action.get("CANONICAL_MODULE_MISSING", 0),
        "findings_by_action": dict(sorted(by_action.items())),
        "findings_by_blocker_level": dict(sorted(by_blocker.items())),
        "domain_summary": domain_summary,
        "wrapper_conversion_ready": direct_root_import_count == 0 and not blockers,
        "wrapper_conversion_blocked": bool(blockers),
        "wrapper_conversion_blocker_count": len(blockers),
        "wrapper_conversion_performed": False,
        "root_package_deletion_performed": False,
        "import_rewrite_performed": False,
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "rows": [asdict(row) for row in rows],
        "recommended_sequence": [
            "Convert only READY_FOR_THIN_WRAPPER modules first.",
            "Do not delete root packages while CANONICAL_MODULE_MISSING rows remain.",
            "For CANONICAL_MODULE_MISSING rows, decide whether to port, retire, or keep explicit legacy wrappers.",
            "After conversion, run direct legacy import compatibility tests.",
            "Only consider deleting root packages after a separate external-compatibility decision.",
        ],
        "next_step": {
            "name": "Step253 v5 Thin Wrapper Conversion Batch 1",
            "goal": "Convert READY_FOR_THIN_WRAPPER root modules into re-export wrappers while leaving missing-canonical modules untouched.",
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "domain",
        "root_module",
        "legacy_module",
        "canonical_module",
        "root_file",
        "canonical_file",
        "canonical_module_exists",
        "recommended_action",
        "blocker_level",
        "missing_canonical_symbols",
        "reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["missing_canonical_symbols"] = "|".join(out.get("missing_canonical_symbols", []))
            writer.writerow({field: out.get(field, "") for field in fields})


def _write_markdown(path: Path, plan: dict[str, Any]) -> None:
    lines = [
        "# Step252 Thin Wrapper Conversion Plan",
        "",
        "Step252 plans root package thin-wrapper conversion after direct root imports have been retired.",
        "",
        "No wrappers are converted and no root package files are deleted in Step252.",
        "",
        "## Summary",
        "",
        f"- status: `{plan['status']}`",
        f"- direct root import finding count: `{plan['direct_root_import_finding_count']}`",
        f"- root direct imports retired: `{plan['root_direct_imports_retired']}`",
        f"- root module count: `{plan['root_module_count']}`",
        f"- ready for thin wrapper: `{plan['ready_for_thin_wrapper_count']}`",
        f"- canonical export repair required: `{plan['canonical_export_repair_required_count']}`",
        f"- canonical module missing: `{plan['canonical_module_missing_count']}`",
        f"- wrapper conversion ready: `{plan['wrapper_conversion_ready']}`",
        f"- wrapper conversion blocked: `{plan['wrapper_conversion_blocked']}`",
        "",
        "## Domain Summary",
        "",
    ]
    for domain, summary in plan["domain_summary"].items():
        lines.extend([
            f"### {domain}",
            "",
            f"- root modules: `{summary['root_module_count']}`",
            f"- canonical modules: `{summary['canonical_module_count']}`",
            f"- ready for thin wrapper: `{summary['ready_for_thin_wrapper_count']}`",
            f"- export repair required: `{summary['canonical_export_repair_required_count']}`",
            f"- canonical module missing: `{summary['canonical_module_missing_count']}`",
            "",
        ])
        if summary["root_modules_without_exact_canonical"]:
            lines.append("Missing exact canonical modules:")
            for module_name in summary["root_modules_without_exact_canonical"]:
                lines.append(f"- `{domain}.{module_name}`")
            lines.append("")
    lines.extend(["## Rows", ""])
    for row in plan["rows"]:
        lines.append(
            f"- `{row['legacy_module']}` → `{row['canonical_module']}` "
            f"action=`{row['recommended_action']}` blocker=`{row['blocker_level']}`"
        )
    lines.extend(["", "## Recommended Sequence", ""])
    for item in plan["recommended_sequence"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Safety Boundary",
        "",
        "Step252 does not enable paper execution, adapter routing, external API calls, Telegram real sends, or live trading.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan thin wrapper conversion for root compatibility packages.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-output", default="data/reports/step252_thin_wrapper_conversion_plan.json")
    parser.add_argument("--csv-output", default="data/reports/step252_thin_wrapper_conversion_plan.csv")
    parser.add_argument("--md-output", default="data/reports/step252_thin_wrapper_conversion_plan.md")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan = build_thin_wrapper_conversion_plan(root)

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
        "root_module_count": plan["root_module_count"],
        "ready_for_thin_wrapper_count": plan["ready_for_thin_wrapper_count"],
        "canonical_module_missing_count": plan["canonical_module_missing_count"],
        "wrapper_conversion_ready": plan["wrapper_conversion_ready"],
        "wrapper_conversion_blocked": plan["wrapper_conversion_blocked"],
        "wrapper_conversion_performed": plan["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
