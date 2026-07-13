from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plan_legacy_root_import_retirement import build_import_retirement_plan


@dataclass
class ManualMappingReviewRow:
    finding_id: str
    file: str
    line: int
    legacy_module: str
    domain: str
    imported_names: str
    canonical_module: str
    root_module_exists: bool
    canonical_exact_module_exists: bool
    canonical_domain_exists: bool
    imported_symbol_count: int
    imported_symbols: list[str]
    root_exported_symbols: list[str]
    canonical_exact_exported_symbols: list[str]
    canonical_domain_symbol_matches: dict[str, list[str]]
    missing_from_root_symbols: list[str]
    missing_from_canonical_exact_symbols: list[str]
    missing_from_canonical_domain_symbols: list[str]
    recommended_action: str
    wrapper_blocker_level: str
    reason: str


def _module_path(root: Path, module_name: str) -> tuple[Path, Path]:
    parts = module_name.split(".")
    return root / Path(*parts).with_suffix(".py"), root / Path(*parts) / "__init__.py"


def _canonical_module_path(root: Path, canonical_module: str) -> tuple[Path, Path]:
    parts = canonical_module.split(".")
    if parts and parts[0] == "crypto_ai_system":
        parts = parts[1:]
    return root / "src" / "crypto_ai_system" / Path(*parts).with_suffix(".py"), root / "src" / "crypto_ai_system" / Path(*parts) / "__init__.py"


def _read_module_text(py_path: Path, pkg_path: Path) -> str:
    if py_path.exists():
        return py_path.read_text(encoding="utf-8", errors="ignore")
    if pkg_path.exists():
        return pkg_path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _exported_symbols_from_text(text: str) -> list[str]:
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


def _split_imported_names(value: str) -> list[str]:
    if not value:
        return []
    out = []
    for part in str(value).split(","):
        name = part.strip()
        if not name or name == "*":
            continue
        # imported_names are plain alias.name from AST in Step240 planner.
        out.append(name)
    return out


def _scan_canonical_domain_for_symbols(root: Path, domain: str, symbols: list[str]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {symbol: [] for symbol in symbols}
    domain_root = root / "src" / "crypto_ai_system" / domain
    if not domain_root.exists():
        return matches
    for path in sorted(domain_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        exported = set(_exported_symbols_from_text(text))
        rel_module = "crypto_ai_system." + ".".join(path.relative_to(root / "src" / "crypto_ai_system").with_suffix("").parts)
        for symbol in symbols:
            if symbol in exported:
                matches[symbol].append(rel_module)
    return {k: v for k, v in matches.items() if v}


def _classify(row: dict[str, Any], root: Path) -> ManualMappingReviewRow:
    legacy_module = row["legacy_module"]
    canonical_module = row["canonical_module"]
    domain = row["domain"]

    root_py, root_pkg = _module_path(root, legacy_module)
    can_py, can_pkg = _canonical_module_path(root, canonical_module)

    root_text = _read_module_text(root_py, root_pkg)
    canonical_text = _read_module_text(can_py, can_pkg)

    root_exists = bool(root_text)
    canonical_exact_exists = bool(canonical_text)
    canonical_domain_exists = (root / "src" / "crypto_ai_system" / domain).exists()

    imported_symbols = _split_imported_names(row.get("imported_names", ""))
    root_exports = _exported_symbols_from_text(root_text)
    canonical_exports = _exported_symbols_from_text(canonical_text)
    canonical_domain_matches = _scan_canonical_domain_for_symbols(root, domain, imported_symbols)

    missing_root = [s for s in imported_symbols if s not in root_exports]
    missing_exact = [s for s in imported_symbols if s not in canonical_exports]
    missing_domain = [s for s in imported_symbols if s not in canonical_domain_matches]

    if canonical_exact_exists and not missing_exact:
        action = "READY_FOR_EXACT_CANONICAL_REWRITE_AFTER_TEST"
        level = "LOW"
        reason = "Exact canonical module exists and exports all imported names."
    elif canonical_domain_exists and imported_symbols and not missing_domain:
        action = "CANONICAL_DOMAIN_SYMBOL_REMAP_REQUIRED"
        level = "MEDIUM"
        reason = "All imported names exist somewhere in canonical domain, but not in exact module path."
    elif canonical_domain_exists and imported_symbols and len(missing_domain) < len(imported_symbols):
        action = "PARTIAL_CANONICAL_PORT_OR_REMAP_REQUIRED"
        level = "MEDIUM"
        reason = "Some imported names exist in canonical domain; missing names require porting or manual mapping."
    elif canonical_domain_exists:
        action = "ROOT_ONLY_FEATURE_PORT_REQUIRED"
        level = "HIGH"
        reason = "Canonical domain exists, but imported names were not found in canonical domain."
    else:
        action = "CANONICAL_DOMAIN_MISSING_KEEP_LEGACY"
        level = "HIGH"
        reason = "Canonical domain does not exist; legacy import must remain."

    if not imported_symbols:
        action = "PACKAGE_OR_MODULE_IMPORT_MANUAL_REVIEW"
        level = "MEDIUM"
        reason = "Import does not specify symbols; manual review is required."

    return ManualMappingReviewRow(
        finding_id=row["finding_id"],
        file=row["file"],
        line=int(row["line"]),
        legacy_module=legacy_module,
        domain=domain,
        imported_names=row.get("imported_names", ""),
        canonical_module=canonical_module,
        root_module_exists=root_exists,
        canonical_exact_module_exists=canonical_exact_exists,
        canonical_domain_exists=canonical_domain_exists,
        imported_symbol_count=len(imported_symbols),
        imported_symbols=imported_symbols,
        root_exported_symbols=root_exports,
        canonical_exact_exported_symbols=canonical_exports,
        canonical_domain_symbol_matches=canonical_domain_matches,
        missing_from_root_symbols=missing_root,
        missing_from_canonical_exact_symbols=missing_exact,
        missing_from_canonical_domain_symbols=missing_domain,
        recommended_action=action,
        wrapper_blocker_level=level,
        reason=reason,
    )


def build_manual_mapping_review(root: Path) -> dict[str, Any]:
    plan = build_import_retirement_plan(root)
    manual_rows = [
        row for row in plan["rows"]
        if row.get("suggested_action") == "MANUAL_MAPPING_REQUIRED"
    ]
    rows = [_classify(row, root) for row in manual_rows]

    by_action: dict[str, int] = {}
    by_level: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for row in rows:
        by_action[row.recommended_action] = by_action.get(row.recommended_action, 0) + 1
        by_level[row.wrapper_blocker_level] = by_level.get(row.wrapper_blocker_level, 0) + 1
        by_domain[row.domain] = by_domain.get(row.domain, 0) + 1

    blocker_count = sum(1 for row in rows if row.wrapper_blocker_level in {"MEDIUM", "HIGH"})

    return {
        "review_type": "legacy_root_manual_mapping_review",
        "status": "REVIEW_ONLY_NO_IMPORT_REWRITE",
        "canonical_package_root": "src/crypto_ai_system",
        "manual_mapping_input_count": len(manual_rows),
        "review_row_count": len(rows),
        "findings_by_recommended_action": dict(sorted(by_action.items())),
        "findings_by_wrapper_blocker_level": dict(sorted(by_level.items())),
        "findings_by_domain": dict(sorted(by_domain.items())),
        "wrapper_conversion_blocked": blocker_count > 0,
        "wrapper_conversion_blocker_count": blocker_count,
        "rewrite_performed": False,
        "wrapper_conversion_performed": False,
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "rows": [asdict(row) for row in rows],
        "next_step": {
            "name": "Step243 v5 Canonical Port Plan for Root-Only Legacy Features",
            "goal": "Port or explicitly map root-only symbols into src/crypto_ai_system before wrapper conversion.",
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "finding_id",
        "file",
        "line",
        "legacy_module",
        "domain",
        "imported_names",
        "canonical_module",
        "root_module_exists",
        "canonical_exact_module_exists",
        "canonical_domain_exists",
        "imported_symbol_count",
        "recommended_action",
        "wrapper_blocker_level",
        "reason",
        "missing_from_canonical_exact_symbols",
        "missing_from_canonical_domain_symbols",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("missing_from_canonical_exact_symbols", "missing_from_canonical_domain_symbols"):
                out[key] = "|".join(out.get(key, []))
            writer.writerow({field: out.get(field, "") for field in fields})


def _write_markdown(path: Path, review: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step242 Legacy Root Manual Mapping Review",
        "",
        "Step242 reviews remaining `MANUAL_MAPPING_REQUIRED` imports after Step241.",
        "",
        "No imports are rewritten and no wrapper conversion is performed in Step242.",
        "",
        "## Summary",
        "",
        f"- status: `{review['status']}`",
        f"- manual mapping input count: `{review['manual_mapping_input_count']}`",
        f"- wrapper conversion blocked: `{review['wrapper_conversion_blocked']}`",
        f"- wrapper conversion blocker count: `{review['wrapper_conversion_blocker_count']}`",
        "",
        "## Findings by recommended action",
        "",
    ]
    for action, count in review["findings_by_recommended_action"].items():
        lines.append(f"- `{action}`: {count}")
    lines.extend(["", "## Findings by blocker level", ""])
    for level, count in review["findings_by_wrapper_blocker_level"].items():
        lines.append(f"- `{level}`: {count}")
    lines.extend(["", "## Rows", ""])
    for row in review["rows"]:
        lines.append(
            f"- `{row['finding_id']}` `{row['file']}:{row['line']}` "
            f"`{row['legacy_module']}` action=`{row['recommended_action']}` "
            f"blocker=`{row['wrapper_blocker_level']}`"
        )
    lines.extend([
        "",
        "## Next step",
        "",
        f"- `{review['next_step']['name']}`",
        f"- Goal: {review['next_step']['goal']}",
        "",
        "## Safety boundary",
        "",
        "Step242 does not enable paper execution, adapter routing, external API calls, Telegram real sends, or live trading.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review manual mapping requirements for legacy root imports.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-output", default="data/reports/step242_legacy_root_manual_mapping_review.json")
    parser.add_argument("--csv-output", default="data/reports/step242_legacy_root_manual_mapping_review.csv")
    parser.add_argument("--md-output", default="data/reports/step242_legacy_root_manual_mapping_review.md")
    parser.add_argument("--fail-if-wrapper-unblocked", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    review = build_manual_mapping_review(root)

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
    json_path.write_text(json.dumps(review, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    _write_csv(csv_path, review["rows"])
    _write_markdown(md_path, review)

    print(json.dumps({
        "status": review["status"],
        "json_output": str(json_path),
        "csv_output": str(csv_path),
        "md_output": str(md_path),
        "manual_mapping_input_count": review["manual_mapping_input_count"],
        "findings_by_recommended_action": review["findings_by_recommended_action"],
        "findings_by_wrapper_blocker_level": review["findings_by_wrapper_blocker_level"],
        "wrapper_conversion_blocked": review["wrapper_conversion_blocked"],
        "wrapper_conversion_blocker_count": review["wrapper_conversion_blocker_count"],
        "rewrite_performed": review["rewrite_performed"],
        "wrapper_conversion_performed": review["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))

    if args.fail_if_wrapper_unblocked and not review["wrapper_conversion_blocked"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
