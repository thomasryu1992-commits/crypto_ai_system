from __future__ import annotations

import argparse
import json
import hashlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

ROOT = bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_approval import (
    STEP261_PROFILE_APPROVAL_PACKET_VERSION,
    apply_step261_approved_profile_disabled_stub,
    build_step261_manual_approval_packet,
    validate_step261_approval_packet,
)
from scripts.report_step260_researchsignal_profile_review_only_calibration import build_report as build_step260_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step260_report(
    root: Path,
    *,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    # If the caller provided replay inputs, rebuild Step260 from those inputs instead of
    # reusing a stale report that may have been created by an earlier test or run.
    prefer_rebuild = step260_report_path is None and (matrix_path is not None or max_rows is not None)
    if step260_report_path:
        p = Path(step260_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    if not prefer_rebuild:
        candidates.extend([
            root / "data/reports/step260_researchsignal_profile_review_only_calibration_report.json",
            root / "storage/latest/step260_researchsignal_profile_review_only_calibration_latest.json",
        ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            return data, str(path.relative_to(root) if path.is_relative_to(root) else path)
    report = build_step260_report(root, matrix_path=matrix_path, max_rows=max_rows)
    generated_path = root / "data/reports/step260_researchsignal_profile_review_only_calibration_report.json"
    latest_path = root / "storage/latest/step260_researchsignal_profile_review_only_calibration_latest.json"
    generated_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    generated_path.write_text(rendered, encoding="utf-8")
    latest_path.write_text(rendered, encoding="utf-8")
    return report, str(generated_path.relative_to(root))


def build_report(
    root: Path,
    *,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    operator_label: str = "manual_reviewer",
    notes: str = "",
) -> dict[str, Any]:
    cfg = load_config(root)
    step260_report, step260_report_source = load_or_build_step260_report(
        root,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    source_path = Path(step260_report_source)
    if not source_path.is_absolute():
        source_path = root / source_path
    packet = build_step261_manual_approval_packet(
        step260_report,
        cfg,
        operator_label=operator_label,
        notes=notes,
        source_step_report_path=source_path,
    )
    validation = validate_step261_approval_packet(packet)
    apply_stub = apply_step261_approved_profile_disabled_stub(packet, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})

    report = {
        "step": 261,
        "status": "completed" if validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_manual_approval_packet_for_review_only_candidate_profile",
        "version": STEP261_PROFILE_APPROVAL_PACKET_VERSION,
        "step260_report_source": step260_report_source,
        "approval_packet": packet,
        "approval_packet_validation": validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "approval_policy": {
            "manual_approval_packet_created": True,
            "manual_approval_required": True,
            "approval_recorded": False,
            "approved_profile_auto_apply_allowed": False,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_deferred": True,
        },
        "safety_boundaries": packet["safety_boundaries"],
        "next_step": {
            "name": "Step262",
            "goal": "Add a separate approval-intake validator for the Step261 packet, still without applying selected ResearchSignal weights.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step261 ResearchSignal profile manual approval packet report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260 report")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding Step260 report")
    parser.add_argument("--operator-label", default="manual_reviewer")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default="data/reports/step261_researchsignal_profile_manual_approval_packet_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step261_researchsignal_profile_manual_approval_packet_latest.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    latest_output = Path(args.latest_output)
    if not output.is_absolute():
        output = root / output
    if not latest_output.is_absolute():
        latest_output = root / latest_output

    report = build_report(
        root,
        step260_report_path=args.step260_report,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        operator_label=args.operator_label,
        notes=args.notes,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    packet = report["approval_packet"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "approval_packet_id": packet["approval_packet_id"],
        "approval_status": packet["approval"]["approval_status"],
        "production_candidate_profile": packet["candidate"]["production_candidate_profile"],
        "candidate_available": packet["candidate"]["candidate_available"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
