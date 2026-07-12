from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

LEGACY_DOMAINS = ("execution", "trading", "research")
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", ".venv", "venv"}


@dataclass
class LegacyDomainInventory:
    domain: str
    root_exists: bool
    canonical_exists: bool
    root_py_file_count: int
    canonical_py_file_count: int
    root_init_marked_compatibility: bool
    canonical_package: str
    migration_status: str


@dataclass
class ImportFinding:
    file: str
    line: int
    import_type: str
    module: str
    domain: str


def _iter_py_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if set(path.relative_to(root).parts) & EXCLUDED_DIRS:
            continue
        yield path


def _module_import_domain(module: str) -> str | None:
    head = module.split(".", 1)[0]
    return head if head in LEGACY_DOMAINS else None


def _scan_imports(root: Path) -> List[ImportFinding]:
    findings: List[ImportFinding] = []
    for path in _iter_py_files(root):
        rel = path.relative_to(root).as_posix()
        # Do not count the legacy package implementation itself as an external dependency on root package.
        if rel.split("/", 1)[0] in LEGACY_DOMAINS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    domain = _module_import_domain(alias.name)
                    if domain:
                        findings.append(ImportFinding(rel, int(getattr(node, "lineno", 0)), "import", alias.name, domain))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                domain = _module_import_domain(module)
                if domain:
                    findings.append(ImportFinding(rel, int(getattr(node, "lineno", 0)), "from", module, domain))
    return findings


def _inventory(root: Path) -> List[LegacyDomainInventory]:
    rows: List[LegacyDomainInventory] = []
    for domain in LEGACY_DOMAINS:
        root_pkg = root / domain
        canonical_pkg = root / "src" / "crypto_ai_system" / domain
        root_init = root_pkg / "__init__.py"
        init_text = root_init.read_text(encoding="utf-8", errors="ignore") if root_init.exists() else ""
        rows.append(
            LegacyDomainInventory(
                domain=domain,
                root_exists=root_pkg.exists(),
                canonical_exists=canonical_pkg.exists(),
                root_py_file_count=len(list(root_pkg.rglob("*.py"))) if root_pkg.exists() else 0,
                canonical_py_file_count=len(list(canonical_pkg.rglob("*.py"))) if canonical_pkg.exists() else 0,
                root_init_marked_compatibility="LEGACY_COMPATIBILITY_PACKAGE = True" in init_text,
                canonical_package=f"crypto_ai_system.{domain}",
                migration_status="wrapper_migration_pending",
            )
        )
    return rows


def build_legacy_root_package_audit(root: Path) -> dict:
    inventory = _inventory(root)
    findings = _scan_imports(root)
    findings_by_domain = {domain: 0 for domain in LEGACY_DOMAINS}
    for finding in findings:
        findings_by_domain[finding.domain] += 1

    return {
        "audit_type": "legacy_root_package_boundary_audit",
        "canonical_package_root": "src/crypto_ai_system",
        "legacy_domains": list(LEGACY_DOMAINS),
        "status": "MIGRATION_PENDING",
        "source_of_truth": "src/crypto_ai_system",
        "root_packages_allowed_only_as_compatibility": True,
        "inventory": [asdict(row) for row in inventory],
        "direct_root_import_finding_count": len(findings),
        "direct_root_import_findings_by_domain": findings_by_domain,
        "direct_root_import_findings": [asdict(f) for f in findings],
        "recommendation": {
            "do_not_add_new_root_feature_logic": True,
            "new_implementation_package": "src/crypto_ai_system",
            "future_step": "Convert root execution/trading/research modules into thin compatibility wrappers after import dependencies are retired.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy root execution/trading/research package boundaries.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="data/reports/step239_legacy_root_package_audit.json")
    parser.add_argument("--fail-on-unmarked-legacy-init", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    audit = build_legacy_root_package_audit(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    unmarked = [
        row["domain"]
        for row in audit["inventory"]
        if row["root_exists"] and not row["root_init_marked_compatibility"]
    ]

    print(json.dumps({
        "status": audit["status"],
        "output": str(output),
        "direct_root_import_finding_count": audit["direct_root_import_finding_count"],
        "unmarked_legacy_init_count": len(unmarked),
        "unmarked_legacy_init": unmarked,
    }, indent=2, ensure_ascii=False))

    if args.fail_on_unmarked_legacy_init and unmarked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
