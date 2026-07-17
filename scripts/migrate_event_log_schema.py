"""One-shot: repair the event-log rows the old bypassing writers left behind.

    py scripts/migrate_event_log_schema.py            # dry run: show what would change
    py scripts/migrate_event_log_schema.py --confirm  # back up + rewrite in place

WHY THIS EXISTS
---------------
Two collectors used to append to the event log directly instead of going through
``log_event``, writing ``{'type': ..., ...}`` where ``log_event`` writes
``{'timestamp', 'event_type', 'severity', 'payload'}``. Those rows therefore read
as ``event_type=None`` to anything that parses the log. PR #35 unified the
writers, so no new ones can appear — this repairs the ones already on disk.

They are NOT junk. Every one is a real ``data_collect_fallback`` or
``data_collect_enrichment_skipped`` event from a real run (a genuine record of
the collector degrading to price-data/mock, or of Coinalyze enrichment being
skipped). Deleting them would throw away real operational history, so this
migrates them into the canonical envelope instead.

THE ONE COMPROMISE
------------------
The old writer never recorded a timestamp, so it cannot be recovered exactly.
The log is append-ordered, so each row is bounded by its neighbours; this takes
the nearest preceding timestamp and marks the row ``timestamp_inferred: true``.
In practice the bound is tight — the neighbours are usually seconds apart — but
the marker means nobody later mistakes an inferred time for a recorded one.
A row with no preceding timestamp (only possible at the head of the file) is
left untouched and reported.

AFTERWARDS
----------
This is a one-shot repair, not a maintained tool. Once it has run and
``--verify`` reports zero malformed rows, delete this file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.time_utils import utc_now  # noqa: E402

DEFAULT_SEVERITY = "INFO"
# Envelope keys log_event writes; everything else on a legacy row is payload.
ENVELOPE = ("timestamp", "event_type", "severity", "payload")


def _log_path() -> Path:
    """Read the path from its single owner rather than resolving it again.

    core/event_log.py is the only module that resolves the log location, and
    tests rebind it there — so a run that forgets --path still cannot reach the
    real log from inside the suite."""
    import core.event_log as event_log

    return Path(event_log.EVENT_LOG_PATH)


def read_rows(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    """Return (rows, unparseable_line_numbers). Blank lines are skipped."""
    rows: list[dict[str, Any]] = []
    bad: list[int] = []
    if not path.exists():
        return rows, bad
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            bad.append(lineno)
            continue
        rows.append(payload if isinstance(payload, dict) else {"_non_object": payload})
    return rows, bad


def is_legacy(row: dict[str, Any]) -> bool:
    """A row the bypassing writer produced: no event_type, but a 'type' tag.

    Deliberately narrow. A row missing event_type for any *other* reason is left
    alone and reported rather than guessed at."""
    return row.get("event_type") is None and isinstance(row.get("type"), str)


def migrate_row(row: dict[str, Any], inferred_timestamp: str | None) -> dict[str, Any] | None:
    """Canonical envelope for one legacy row, or None if its time is unknowable."""
    if inferred_timestamp is None:
        return None
    payload = {k: v for k, v in row.items() if k != "type"}
    return {
        "timestamp": inferred_timestamp,
        "event_type": row["type"],
        "severity": DEFAULT_SEVERITY,
        "payload": payload,
        # The old writer stored no time; this one was read off the preceding row.
        "timestamp_inferred": True,
        "schema_migrated": True,
    }


def plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk the log in order, carrying the last real timestamp forward."""
    migrated: list[dict[str, Any]] = []
    last_timestamp: str | None = None
    counts: dict[str, int] = {}
    unresolved = 0
    other_malformed = 0

    for row in rows:
        if is_legacy(row):
            new_row = migrate_row(row, last_timestamp)
            if new_row is None:
                unresolved += 1
                migrated.append(row)
                continue
            counts[row["type"]] = counts.get(row["type"], 0) + 1
            migrated.append(new_row)
            continue
        if row.get("event_type") is None:
            other_malformed += 1
        timestamp = row.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            last_timestamp = timestamp
        migrated.append(row)

    return {
        "rows": migrated,
        "counts": counts,
        "migrated_total": sum(counts.values()),
        "unresolved_timestamp": unresolved,
        "other_malformed": other_malformed,
    }


def verify(path: Path) -> int:
    rows, bad = read_rows(path)
    malformed = [r for r in rows if r.get("event_type") is None]
    legacy = [r for r in malformed if is_legacy(r)]
    print(f"=== verify {path} ===")
    print(f"  rows                : {len(rows)}")
    print(f"  unparseable lines   : {len(bad)}")
    print(f"  event_type missing  : {len(malformed)}")
    print(f"    of which legacy   : {len(legacy)}")
    if not malformed and not bad:
        print("  OK: every row is canonical. This script has done its job — delete it.")
        return 0
    print("  still malformed — re-run with --confirm, or investigate the rows above.")
    return 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Repair legacy event-log rows written without an envelope.")
    parser.add_argument("--confirm", action="store_true", help="apply (otherwise dry run)")
    parser.add_argument("--verify", action="store_true", help="report malformed rows and exit")
    parser.add_argument("--path", default=None, help="event log to operate on (default: settings.EVENT_LOG_PATH)")
    args = parser.parse_args(argv)

    path = Path(args.path) if args.path else _log_path()
    if args.verify:
        return verify(path)

    if not path.exists():
        print(f"no event log at {path} — nothing to do.")
        return 0

    rows, bad = read_rows(path)
    result = plan(rows)

    print("=== migrate event log schema " + ("(APPLY)" if args.confirm else "(dry run)") + " ===")
    print(f"  file                : {path}")
    print(f"  rows                : {len(rows)}")
    if bad:
        print(f"  unparseable lines   : {len(bad)} (left untouched: {bad[:5]}{'...' if len(bad) > 5 else ''})")
    for event_type, count in sorted(result["counts"].items()):
        verb = "migrated" if args.confirm else "would migrate"
        print(f"  {verb:14} {count:>5}  {event_type}")
    print(f"  total               : {result['migrated_total']}")
    if result["unresolved_timestamp"]:
        print(f"  no preceding timestamp, left as-is: {result['unresolved_timestamp']}")
    if result["other_malformed"]:
        print(f"  malformed but not legacy, left as-is: {result['other_malformed']}")

    if not args.confirm:
        print("dry run only — re-run with --confirm to apply.")
        return 0

    if not result["migrated_total"]:
        print("nothing to migrate.")
        return 0

    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    backup_dir = ROOT / "storage" / "backup" / f"event_log_migration_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)

    # Write beside the original and swap, so an interrupted run cannot leave a
    # half-written log where a complete one used to be.
    tmp = path.with_suffix(path.suffix + ".migrating")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in result["rows"]:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)

    print(f"backup: {backup_dir / path.name}")
    print("done — re-run with --verify to confirm, then delete this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
