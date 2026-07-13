from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

DEFAULT_OUTPUT = "dist/crypto_ai_system_source_handoff.zip"

EXCLUDED_DIR_PARTS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_PREFIXES = {
    "data/reports",
    "data/stores",
    # Source handoff should not carry runtime outputs. Keep source fixtures under
    # data/price_data and data/raw, but strip generated storage artifacts entirely.
    "storage",
    "dist",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".zip"}


def should_exclude(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    rel_posix = rel.as_posix()
    if set(rel.parts) & EXCLUDED_DIR_PARTS:
        return True
    if any(rel_posix == prefix or rel_posix.startswith(prefix + "/") for prefix in EXCLUDED_PREFIXES):
        return True
    if any(rel_posix.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    return False


def build_source_package(root: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_dir() or should_exclude(path, root):
                continue
            zf.write(path, Path("crypto_ai_system_source") / path.relative_to(root))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean source handoff ZIP.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output ZIP path")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    print(build_source_package(root, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
