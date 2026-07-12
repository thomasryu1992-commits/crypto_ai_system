from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

DEFAULT_OUTPUT = "dist/crypto_ai_system_validation_bundle.zip"

INCLUDED_PREFIXES = {
    "data/reports",
    "data/stores",
    "storage/latest",
    "storage/logs",
    "storage/registries",
    "docs",
}
INCLUDED_NAMES = {
    "VALIDATION_REPORT_STEP237.md",
    "VALIDATION_SUMMARY_STEP237.json",
    "VALIDATION_SUMMARY_STEP238.json",
    "STEP238_RUNTIME_PACKAGING_REPAIR_REPORT.md",
}
EXCLUDED_DIR_PARTS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    rel_posix = rel.as_posix()
    if set(rel.parts) & EXCLUDED_DIR_PARTS:
        return False
    if any(rel_posix.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return False
    if rel.name in INCLUDED_NAMES:
        return True
    if len(rel.parts) == 1 and (rel.name.startswith("STEP") or rel.name.startswith("VALIDATION") or rel.name.startswith("README")):
        return True
    return any(rel_posix == prefix or rel_posix.startswith(prefix + "/") for prefix in INCLUDED_PREFIXES)


def build_audit_bundle(root: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    wrote_data_reports = False
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_dir() or not should_include(path, root):
                continue
            rel = path.relative_to(root).as_posix()
            if rel == "data/reports" or rel.startswith("data/reports/"):
                wrote_data_reports = True
            zf.write(path, Path("crypto_ai_system_validation") / path.relative_to(root))
        if not wrote_data_reports:
            zf.writestr("crypto_ai_system_validation/data/reports/.gitkeep", "")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a validation artifact ZIP with runtime outputs separated from source handoff.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output ZIP path")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    print(build_audit_bundle(root, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
