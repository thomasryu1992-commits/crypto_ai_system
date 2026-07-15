"""Reset accumulated paper outcomes so real-data measurement starts clean.

Backs up each target to ``storage/backup/reset_<utc>/`` before clearing, so the
reset is reversible. Dry-run by default; pass --confirm to apply.

    py scripts/reset_paper_outcomes.py            # dry run: show what would clear
    py scripts/reset_paper_outcomes.py --confirm  # back up + clear core targets
    py scripts/reset_paper_outcomes.py --confirm --all  # also derived registries

Core targets: the outcome feedback registry (drives the performance report),
paper trades (risk-guard history), and paper state (open position). --all also
clears derived registries (performance report, candidate profiles, decision
pipeline). Config and code are never touched.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.time_utils import utc_now  # noqa: E402

CORE_REGISTRIES = ("outcome_feedback_registry",)
DERIVED_REGISTRIES = (
    "performance_report_registry",
    "candidate_profile_registry",
    "decision_pipeline_registry",
)

# kind -> empty content written on reset
EMPTY = {
    "jsonl": "",
    "json_list": "[]",
    "paper_state": '{"active_position": null, "closed_trades": []}',
}


def _count(path: Path, kind: str) -> int:
    if not path.exists():
        return 0
    if kind == "jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if kind == "json_list":
        import json

        try:
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0
    return 1 if path.stat().st_size else 0


def discover_targets(include_derived: bool):
    import config.settings as settings
    from crypto_ai_system.config import load_config
    from crypto_ai_system.registry.base_registry import registry_path

    cfg = load_config(".")
    names = list(CORE_REGISTRIES) + (list(DERIVED_REGISTRIES) if include_derived else [])
    targets = [{"name": n, "path": registry_path(cfg, n), "kind": "jsonl"} for n in names]
    targets.append({"name": "paper_trades", "path": Path(settings.PAPER_TRADES_PATH), "kind": "json_list"})
    targets.append({"name": "paper_state", "path": Path(settings.PAPER_STATE_PATH), "kind": "paper_state"})
    return targets


def reset_target(target: dict, backup_dir: Path | None) -> dict:
    path: Path = target["path"]
    kind: str = target["kind"]
    count = _count(path, kind)
    backed_up = False
    if backup_dir is not None and path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)
        backed_up = True
    if backup_dir is not None:  # apply mode
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(EMPTY[kind], encoding="utf-8")
    return {"name": target["name"], "path": str(path), "records": count, "backed_up": backed_up}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Reset accumulated paper outcomes.")
    parser.add_argument("--confirm", action="store_true", help="apply (otherwise dry run)")
    parser.add_argument("--all", action="store_true", help="also clear derived registries")
    args = parser.parse_args(argv)

    targets = discover_targets(include_derived=args.all)

    backup_dir = None
    if args.confirm:
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        backup_dir = ROOT / "storage" / "backup" / f"reset_{stamp}"

    print("=== reset paper outcomes " + ("(APPLY)" if args.confirm else "(dry run)") + " ===")
    total = 0
    for target in targets:
        result = reset_target(target, backup_dir)
        total += result["records"]
        action = "cleared" if args.confirm else "would clear"
        print(f"  {action} {result['name']:28} {result['records']:>6} records"
              + ("  [backed up]" if result["backed_up"] else ""))
    print(f"total records: {total}")
    if args.confirm:
        print(f"backup: {backup_dir}")
    else:
        print("dry run only — re-run with --confirm to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
