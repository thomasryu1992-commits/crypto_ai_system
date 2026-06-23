from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

from config.settings import WIKI_DIR, ensure_base_dirs


def now_kst_label() -> str:
    utc_now = datetime.now(timezone.utc)
    return utc_now.strftime("%Y-%m-%d %H:%M UTC")


def write_markdown(path: str | Path, content: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def wiki_path(*parts: str) -> Path:
    ensure_base_dirs()
    return WIKI_DIR.joinpath(*parts)


def markdown_doc(title: str, sections: Dict[str, str]) -> str:
    lines = [f"# {title}", ""]
    for heading, body in sections.items():
        lines.append(f"## {heading}")
        lines.append(str(body).strip() if str(body).strip() else "TBD")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def update_log(added: Iterable[str], updated: Iterable[str], reason: str) -> Path:
    path = wiki_path("log.md")
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Knowledge Base Log\n"
    entry = ["", f"## {now_kst_label()}", "", "### Added"]
    for item in added:
        entry.append(f"- [[{item}]]")
    entry.append("")
    entry.append("### Updated")
    for item in updated:
        entry.append(f"- [[{item}]]")
    entry.extend(["", "### Reason", f"- {reason}", ""])
    return write_markdown(path, existing.rstrip() + "\n" + "\n".join(entry))


def update_index() -> Path:
    sections = {
        "Sources": "\n".join(_links_for("source")) or "TBD",
        "Entities": "\n".join(_links_for("entity")) or "TBD",
        "Concepts": "\n".join(_links_for("concept")) or "TBD",
        "Scenarios": "\n".join(_links_for("scenario")) or "TBD",
        "Reports": "\n".join(_links_for("report/daily")) or "TBD",
        "Last Updated": now_kst_label(),
    }
    return write_markdown(wiki_path("index.md"), markdown_doc("Crypto AI System Knowledge Index", sections))


def _links_for(relative_folder: str) -> List[str]:
    folder = wiki_path(*relative_folder.split("/"))
    if not folder.exists():
        return []
    links = []
    for path in sorted(folder.glob("*.md")):
        rel = path.relative_to(WIKI_DIR).with_suffix("").as_posix()
        links.append(f"- [[{rel}]]")
    return links
