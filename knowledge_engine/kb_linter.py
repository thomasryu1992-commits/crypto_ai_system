from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config.settings import LINT_DIR, WIKI_DIR, env_bool, ensure_base_dirs
from scripts.json_utils import append_json_log, save_json

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

REQUIRED_SECTIONS = {
    "entity": ["Type", "Current Thesis", "Key Metrics", "Related Concepts", "Last Updated"],
    "concept": ["Definition", "Bullish Interpretation", "Bearish Interpretation", "Risk", "Related Entities"],
    "scenario": ["Status", "Direction", "Core Thesis", "Conditions", "Invalidation", "Trading Implication", "Confidence", "Last Updated"],
    "report/daily": ["Market Summary", "Key Observations", "Active Scenarios", "Trading Bias", "Conditional Setup", "Risk Notes", "Final Decision"],
}


def run_kb_lint() -> Dict[str, Any]:
    ensure_base_dirs()
    LINT_DIR.mkdir(parents=True, exist_ok=True)
    checks: List[Dict[str, Any]] = []

    checks.extend(_check_required_top_files())
    checks.extend(_check_required_sections())
    checks.extend(_check_broken_links())
    checks.extend(_check_orphan_notes())
    checks.extend(_check_duplicate_entities())
    checks.extend(_check_trading_decision_safety())

    error_count = sum(1 for check in checks if check.get("level") == "ERROR" and not check.get("passed"))
    warning_count = sum(1 for check in checks if check.get("level") == "WARNING" and not check.get("passed"))

    if error_count > 0:
        status = "ERROR"
    elif warning_count > 0:
        status = "PASSED_WITH_WARNINGS"
    else:
        status = "PASSED"

    result = {
        "step": "KB_LINT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "passed": status != "ERROR",
        "error_count": error_count,
        "warning_count": warning_count,
        "checks": checks,
        "failed_checks": [check for check in checks if not check.get("passed")],
        "policy": {
            "block_trading_on_error": env_bool("KB_LINT_BLOCK_TRADING_ON_ERROR", True),
        },
    }
    result_path = LINT_DIR / "kb_lint_result.json"
    log_path = LINT_DIR / "kb_lint_log.json"
    save_json(result_path, result)
    append_json_log(log_path, result)
    return result


def _check_required_top_files() -> List[Dict[str, Any]]:
    checks = []
    for name in ["hot.md", "index.md", "log.md"]:
        path = WIKI_DIR / name
        checks.append({
            "name": "REQUIRED_TOP_FILE",
            "level": "ERROR",
            "passed": path.exists(),
            "file": str(path),
            "message": f"{name} exists." if path.exists() else f"{name} is missing.",
        })
    return checks


def _check_required_sections() -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for folder, sections in REQUIRED_SECTIONS.items():
        base = WIKI_DIR.joinpath(*folder.split("/"))
        for path in sorted(base.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for section in sections:
                exists = f"## {section}" in text
                checks.append({
                    "name": "REQUIRED_SECTION",
                    "level": "ERROR" if folder.startswith("scenario") and section == "Invalidation" else "WARNING",
                    "passed": exists,
                    "file": str(path),
                    "section": section,
                    "message": f"Section {section} exists." if exists else f"Section {section} is missing.",
                })
    return checks


def _check_broken_links() -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for path in WIKI_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for raw_link in WIKI_LINK_RE.findall(text):
            target = raw_link.split("|")[0].strip()
            if target.startswith("../"):
                candidate = (path.parent / target).with_suffix(".md").resolve()
            else:
                candidate = (WIKI_DIR / target).with_suffix(".md").resolve()
            passed = candidate.exists()
            checks.append({
                "name": "BROKEN_WIKI_LINK",
                "level": "ERROR",
                "passed": passed,
                "file": str(path),
                "link": raw_link,
                "target": str(candidate),
                "message": "Wiki link resolved." if passed else "Broken wiki link detected.",
            })
    return checks


def _check_orphan_notes() -> List[Dict[str, Any]]:
    all_notes = {p.relative_to(WIKI_DIR).with_suffix("").as_posix(): p for p in WIKI_DIR.rglob("*.md")}
    linked = set()
    for path in WIKI_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for raw_link in WIKI_LINK_RE.findall(text):
            linked.add(raw_link.split("|")[0].strip().replace("../", ""))
    checks = []
    for note, path in all_notes.items():
        if note in {"index", "hot", "log"}:
            continue
        passed = note in linked or note.startswith("report/daily/")
        checks.append({
            "name": "ORPHAN_NOTE",
            "level": "WARNING",
            "passed": passed,
            "file": str(path),
            "note": note,
            "message": "Note is linked or report note." if passed else "Orphan note detected.",
        })
    return checks


def _check_duplicate_entities() -> List[Dict[str, Any]]:
    entity_dir = WIKI_DIR / "entity"
    seen: Dict[str, str] = {}
    checks: List[Dict[str, Any]] = []
    for path in sorted(entity_dir.glob("*.md")):
        key = path.stem.lower()
        duplicate = key in seen
        checks.append({
            "name": "DUPLICATE_ENTITY",
            "level": "WARNING",
            "passed": not duplicate,
            "file": str(path),
            "message": "No duplicate entity slug." if not duplicate else f"Duplicate-like entity detected with {seen[key]}.",
        })
        seen[key] = str(path)
    return checks


def _check_trading_decision_safety() -> List[Dict[str, Any]]:
    latest = WIKI_DIR / "report" / "daily" / "latest.md"
    checks = []
    exists = latest.exists()
    checks.append({
        "name": "LATEST_REPORT_EXISTS",
        "level": "ERROR",
        "passed": exists,
        "file": str(latest),
        "message": "Latest report exists." if exists else "Latest report is missing.",
    })
    if not exists:
        return checks
    text = latest.read_text(encoding="utf-8")
    for section in ["Final Decision", "Conditional Setup", "Risk Notes"]:
        passed = f"## {section}" in text
        checks.append({
            "name": "TRADING_DECISION_SECTION",
            "level": "ERROR",
            "passed": passed,
            "file": str(latest),
            "section": section,
            "message": f"{section} exists." if passed else f"{section} is missing.",
        })
    return checks


if __name__ == "__main__":
    result = run_kb_lint()
    print(f"KB Lint Status: {result.get('status')}")
    print(f"Errors: {result.get('error_count')}, Warnings: {result.get('warning_count')}")
