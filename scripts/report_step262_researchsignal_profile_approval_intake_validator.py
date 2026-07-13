from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

ROOT = bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_approval_intake import (
    STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
    apply_step262_approval_intake_disabled_stub,
    build_step262_approval_intake_record,
    validate_step262_approval_intake_record,
)
from scripts.report_step261_researchsignal_profile_manual_approval_packet import build_report as build_step261_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step261_report(
    root: Path,
    *,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step261_report_path:
        p = Path(step261_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step261_researchsignal_profile_manual_approval_packet_report.json",
        root / "storage/latest/step261_researchsignal_profile_manual_approval_packet_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            return data, str(path.relative_to(root) if path.is_relative_to(root) else path)
    return (
        build_step261_report(
            root,
            step260_report_path=step260_report_path,
            matrix_path=matrix_path,
            max_rows=max_rows,
        ),
        "rebuilt_step261_report",
    )


def build_report(
    root: Path,
    *,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    rationale: str = "Step262 default review-only intake validation run.",
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    step261_report, step261_report_source = load_or_build_step261_report(
        root,
        step261_report_path=step261_report_path,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    intake_record = build_step262_approval_intake_record(
        step261_report,
        cfg,
        approval_decision=approval_decision,
        approver=approver,
        rationale=rationale,
        timestamp_utc=timestamp_utc,
        metadata={"source": "step262_report_script"},
    )
    intake_validation = validate_step262_approval_intake_record(intake_record)
    apply_stub = apply_step262_approval_intake_disabled_stub(intake_record, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})

    report = {
        "step": 262,
        "status": "completed" if intake_validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_approval_intake_validator_review_only",
        "version": STEP262_PROFILE_APPROVAL_INTAKE_VERSION,
        "step261_report_source": step261_report_source,
        "approval_intake_record": intake_record,
        "approval_intake_validation": intake_validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "approval_intake_policy": {
            "approval_intake_record_created": True,
            "approval_intake_validation_only": True,
            "approve_for_review_only_staging_is_not_runtime_apply": True,
            "approved_profile_auto_apply_allowed": False,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_deferred": True,
        },
        "safety_boundaries": intake_record["safety_boundaries"],
        "next_step": {
            "name": "Step263",
            "goal": "Design the next review-only staging handoff for an approved ResearchSignal profile, still without mutating runtime score weights.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step262 ResearchSignal profile approval-intake validator report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260/Step261")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--approver", default="manual_reviewer")
    parser.add_argument("--rationale", default="Step262 default review-only intake validation run.")
    parser.add_argument("--timestamp-utc", default=None)
    parser.add_argument("--output", default="data/reports/step262_researchsignal_profile_approval_intake_validator_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step262_researchsignal_profile_approval_intake_validator_latest.json")
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
        step261_report_path=args.step261_report,
        step260_report_path=args.step260_report,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        approval_decision=args.approval_decision,
        approver=args.approver,
        rationale=args.rationale,
        timestamp_utc=args.timestamp_utc,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    record = report["approval_intake_record"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "approval_packet_id": record["approval_packet_id"],
        "approval_decision": record["approval_record"]["approval_decision"],
        "record_status": record["approval_record"]["record_status"],
        "recorded": record["approval_record"]["recorded"],
        "production_candidate_profile": record["production_candidate_profile"],
        "candidate_available": record["candidate_available"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
