from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

LEGACY_DOMAINS = ("execution", "trading", "research")
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", ".venv", "venv"}


@dataclass
class ImportFinding:
    file: str
    line: int
    import_type: str
    module: str
    domain: str
    imported_names: str


@dataclass
class RetirementPlanRow:
    finding_id: str
    file: str
    line: int
    import_type: str
    legacy_module: str
    domain: str
    imported_names: str
    canonical_module: str
    canonical_module_exists: bool
    canonical_domain_exists: bool
    suggested_action: str
    risk_level: str
    reason: str


def _iter_py_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if set(rel.parts) & EXCLUDED_DIRS:
            continue
        yield path


def _legacy_domain(module: str) -> str | None:
    head = module.split(".", 1)[0]
    return head if head in LEGACY_DOMAINS else None


def _scan_imports(root: Path) -> List[ImportFinding]:
    findings: List[ImportFinding] = []
    for path in _iter_py_files(root):
        rel = path.relative_to(root).as_posix()
        if rel.split("/", 1)[0] in LEGACY_DOMAINS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    domain = _legacy_domain(alias.name)
                    if domain:
                        findings.append(
                            ImportFinding(
                                file=rel,
                                line=int(getattr(node, "lineno", 0)),
                                import_type="import",
                                module=alias.name,
                                domain=domain,
                                imported_names=alias.asname or "",
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                domain = _legacy_domain(module)
                if domain:
                    names = ",".join(alias.name for alias in node.names)
                    findings.append(
                        ImportFinding(
                            file=rel,
                            line=int(getattr(node, "lineno", 0)),
                            import_type="from",
                            module=module,
                            domain=domain,
                            imported_names=names,
                        )
                    )
    return findings


def _canonical_module_for(legacy_module: str) -> str:
    return f"crypto_ai_system.{legacy_module}"


def _canonical_path(root: Path, canonical_module: str) -> tuple[Path, Path]:
    parts = canonical_module.split(".")
    if parts[:2] != ["crypto_ai_system", parts[1]]:
        # not expected; still provide deterministic path
        pass
    relative = Path(*parts[1:])
    return root / "src" / "crypto_ai_system" / relative.with_suffix(".py"), root / "src" / "crypto_ai_system" / relative / "__init__.py"


def _classify(root: Path, finding: ImportFinding, idx: int) -> RetirementPlanRow:
    canonical_module = _canonical_module_for(finding.module)
    py_path, pkg_path = _canonical_path(root, canonical_module)
    canonical_module_exists = py_path.exists() or pkg_path.exists()
    canonical_domain_exists = (root / "src" / "crypto_ai_system" / finding.domain).exists()

    if canonical_module_exists:
        action = "READY_FOR_CANONICAL_IMPORT_REWRITE"
        risk = "LOW"
        reason = "Exact canonical module path exists under src/crypto_ai_system."
    elif finding.module == finding.domain and canonical_domain_exists:
        action = "READY_FOR_PACKAGE_LEVEL_CANONICAL_IMPORT_REWRITE"
        risk = "LOW"
        reason = "Canonical domain package exists, and the import targets the package root."
    elif canonical_domain_exists:
        action = "MANUAL_MAPPING_REQUIRED"
        risk = "MEDIUM"
        reason = "Canonical domain exists, but the exact module path does not. Manual equivalence mapping is required before rewriting."
    else:
        action = "KEEP_LEGACY_TEMPORARY"
        risk = "HIGH"
        reason = "Canonical domain package is missing. Keep legacy import until a canonical module is created."

    return RetirementPlanRow(
        finding_id=f"legacy_import_{idx:03d}",
        file=finding.file,
        line=finding.line,
        import_type=finding.import_type,
        legacy_module=finding.module,
        domain=finding.domain,
        imported_names=finding.imported_names,
        canonical_module=canonical_module,
        canonical_module_exists=canonical_module_exists,
        canonical_domain_exists=canonical_domain_exists,
        suggested_action=action,
        risk_level=risk,
        reason=reason,
    )


def build_import_retirement_plan(root: Path) -> dict:
    findings = _scan_imports(root)
    rows = [_classify(root, finding, idx) for idx, finding in enumerate(findings, start=1)]
    by_action: dict[str, int] = {}
    by_domain: dict[str, int] = {domain: 0 for domain in LEGACY_DOMAINS}
    by_risk: dict[str, int] = {}
    for row in rows:
        by_action[row.suggested_action] = by_action.get(row.suggested_action, 0) + 1
        by_domain[row.domain] = by_domain.get(row.domain, 0) + 1
        by_risk[row.risk_level] = by_risk.get(row.risk_level, 0) + 1

    return {
        "plan_type": "legacy_root_import_retirement_plan",
        "status": "PLAN_ONLY_NO_IMPORT_REWRITE",
        "canonical_package_root": "src/crypto_ai_system",
        "legacy_domains": list(LEGACY_DOMAINS),
        "direct_root_import_finding_count": len(rows),
        "findings_by_domain": by_domain,
        "findings_by_action": dict(sorted(by_action.items())),
        "findings_by_risk": dict(sorted(by_risk.items())),
        "rewrite_performed": False,
        "wrapper_conversion_performed": False,
        "live_trading_allowed": False,
        "paper_execution_enabled": False,
        "adapter_routing_enabled": False,
        "rows": [asdict(row) for row in rows],
        "next_step": {
            "name": "Step241 v5 Legacy Root Import Rewrite Candidate Patch",
            "safe_first_action": "Rewrite LOW-risk exact canonical import candidates only, then rerun full tests.",
            "blocked_action": "Do not convert root packages to thin wrappers until MANUAL_MAPPING_REQUIRED rows are resolved.",
        },
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "finding_id",
        "file",
        "line",
        "import_type",
        "legacy_module",
        "domain",
        "imported_names",
        "canonical_module",
        "canonical_module_exists",
        "canonical_domain_exists",
        "suggested_action",
        "risk_level",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_markdown(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Step240 Legacy Root Import Retirement Plan",
        "",
        "This report classifies direct imports from root-level `execution`, `trading`, and `research` packages.",
        "",
        "No imports are rewritten in Step240. No wrapper conversion is performed in Step240.",
        "",
        "## Summary",
        "",
        f"- status: `{plan['status']}`",
        f"- canonical package root: `{plan['canonical_package_root']}`",
        f"- direct root import finding count: `{plan['direct_root_import_finding_count']}`",
        f"- rewrite performed: `{plan['rewrite_performed']}`",
        f"- wrapper conversion performed: `{plan['wrapper_conversion_performed']}`",
        "",
        "## Findings by action",
        "",
    ]
    for action, count in plan["findings_by_action"].items():
        lines.append(f"- `{action}`: {count}")
    lines.extend(["", "## Findings by risk", ""])
    for risk, count in plan["findings_by_risk"].items():
        lines.append(f"- `{risk}`: {count}")
    lines.extend(["", "## Import retirement rows", ""])
    for row in plan["rows"]:
        lines.append(
            f"- `{row['finding_id']}` `{row['file']}:{row['line']}` "
            f"`{row['legacy_module']}` → `{row['canonical_module']}` "
            f"action=`{row['suggested_action']}` risk=`{row['risk_level']}`"
        )
    lines.extend([
        "",
        "## Next step",
        "",
        f"- `{plan['next_step']['name']}`",
        f"- Safe first action: {plan['next_step']['safe_first_action']}",
        f"- Blocked action: {plan['next_step']['blocked_action']}",
        "",
        "## Safety boundary",
        "",
        "Step240 does not enable paper execution, adapter routing, external API calls, Telegram real sends, or live trading.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a retirement plan for legacy root imports.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-output", default="data/reports/step240_legacy_root_import_retirement_plan.json")
    parser.add_argument("--csv-output", default="data/reports/step240_legacy_root_import_retirement_plan.csv")
    parser.add_argument("--md-output", default="data/reports/step240_legacy_root_import_retirement_plan.md")
    parser.add_argument("--max-high-risk", type=int, default=9999)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan = build_import_retirement_plan(root)

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

    high_risk_count = plan["findings_by_risk"].get("HIGH", 0)

    print(json.dumps({
        "status": plan["status"],
        "json_output": str(json_path),
        "csv_output": str(csv_path),
        "md_output": str(md_path),
        "direct_root_import_finding_count": plan["direct_root_import_finding_count"],
        "findings_by_action": plan["findings_by_action"],
        "findings_by_risk": plan["findings_by_risk"],
        "rewrite_performed": plan["rewrite_performed"],
        "wrapper_conversion_performed": plan["wrapper_conversion_performed"],
    }, indent=2, ensure_ascii=False))

    if high_risk_count > args.max_high_risk:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
