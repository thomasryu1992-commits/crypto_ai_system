from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_apply_dry_run import (
    STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
    apply_step265_disabled_apply_candidate_dry_run_stub,
    build_step265_disabled_apply_candidate_dry_run_packet,
    validate_step265_disabled_apply_candidate_dry_run_packet,
)
from scripts.report_step264_researchsignal_profile_pre_apply_review_validator import build_report as build_step264_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step264_report(
    root: Path,
    *,
    step264_report_path: str | None = None,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    approval_rationale: str = "Step265 default upstream approval-intake rebuild.",
    approval_timestamp_utc: str | None = None,
    review_decision: str = "REQUEST_MORE_DATA",
    reviewer: str = "manual_pre_apply_reviewer",
    review_rationale: str = "Step265 default upstream pre-apply review rebuild.",
    review_timestamp_utc: str | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step264_report_path:
        p = Path(step264_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step264_researchsignal_profile_pre_apply_review_validator_report.json",
        root / "storage/latest/step264_researchsignal_profile_pre_apply_review_validator_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            try:
                return data, str(path.relative_to(root))
            except ValueError:
                return data, str(path)
    return (
        build_step264_report(
            root,
            step263_report_path=step263_report_path,
            step262_report_path=step262_report_path,
            step261_report_path=step261_report_path,
            step260_report_path=step260_report_path,
            matrix_path=matrix_path,
            max_rows=max_rows,
            approval_decision=approval_decision,
            approver=approver,
            approval_rationale=approval_rationale,
            approval_timestamp_utc=approval_timestamp_utc,
            review_decision=review_decision,
            reviewer=reviewer,
            rationale=review_rationale,
            timestamp_utc=review_timestamp_utc,
        ),
        "rebuilt_step264_report",
    )


def build_report(
    root: Path,
    *,
    step264_report_path: str | None = None,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    approval_rationale: str = "Step265 default upstream approval-intake rebuild.",
    approval_timestamp_utc: str | None = None,
    review_decision: str = "REQUEST_MORE_DATA",
    reviewer: str = "manual_pre_apply_reviewer",
    review_rationale: str = "Step265 default upstream pre-apply review rebuild.",
    review_timestamp_utc: str | None = None,
    operator_label: str = "manual_apply_dry_run_reviewer",
    notes: str = "Step265 default disabled apply-candidate dry-run packet.",
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    step264_report, step264_report_source = load_or_build_step264_report(
        root,
        step264_report_path=step264_report_path,
        step263_report_path=step263_report_path,
        step262_report_path=step262_report_path,
        step261_report_path=step261_report_path,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
        approval_decision=approval_decision,
        approver=approver,
        approval_rationale=approval_rationale,
        approval_timestamp_utc=approval_timestamp_utc,
        review_decision=review_decision,
        reviewer=reviewer,
        review_rationale=review_rationale,
        review_timestamp_utc=review_timestamp_utc,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    packet = build_step265_disabled_apply_candidate_dry_run_packet(
        step264_report,
        cfg,
        operator_label=operator_label,
        notes=notes,
        timestamp_utc=timestamp_utc,
    )
    validation = validate_step265_disabled_apply_candidate_dry_run_packet(packet)
    apply_stub = apply_step265_disabled_apply_candidate_dry_run_stub(packet, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})

    dry_run = packet["dry_run"]
    report = {
        "step": 265,
        "status": "completed" if validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_disabled_apply_candidate_dry_run_diff_packet",
        "version": STEP265_PROFILE_APPLY_DRY_RUN_VERSION,
        "step264_report_source": step264_report_source,
        "apply_dry_run_packet": packet,
        "apply_dry_run_validation": validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "apply_dry_run_policy": {
            "dry_run_packet_created": True,
            "dry_run_status": dry_run["dry_run_status"],
            "ready_for_disabled_apply_dry_run": dry_run["ready_for_disabled_apply_dry_run"],
            "candidate_settings_diff_created": True,
            "mutation_plan_created_but_disabled": True,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_deferred": True,
        },
        "safety_boundaries": packet["safety_boundaries"],
        "next_step": {
            "name": "Step266",
            "goal": "Add manual final-apply approval validator for the Step265 dry-run packet while keeping score_weights mutation disabled.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step265 ResearchSignal disabled apply-candidate dry-run report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step264-report", default=None, help="Optional Step264 report JSON path")
    parser.add_argument("--step263-report", default=None, help="Optional Step263 report JSON path when rebuilding Step264")
    parser.add_argument("--step262-report", default=None, help="Optional Step262 report JSON path when rebuilding Step263/264")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path when rebuilding Step262+")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261+")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260+ chain")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--approver", default="manual_reviewer")
    parser.add_argument("--approval-rationale", default="Step265 default upstream approval-intake rebuild.")
    parser.add_argument("--approval-timestamp-utc", default=None)
    parser.add_argument("--review-decision", default="REQUEST_MORE_DATA", choices=["READY", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--reviewer", default="manual_pre_apply_reviewer")
    parser.add_argument("--review-rationale", default="Step265 default upstream pre-apply review rebuild.")
    parser.add_argument("--review-timestamp-utc", default=None)
    parser.add_argument("--operator-label", default="manual_apply_dry_run_reviewer")
    parser.add_argument("--notes", default="Step265 default disabled apply-candidate dry-run packet.")
    parser.add_argument("--timestamp-utc", default=None)
    parser.add_argument("--output", default="data/reports/step265_researchsignal_profile_disabled_apply_dry_run_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step265_researchsignal_profile_disabled_apply_dry_run_latest.json")
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
        step264_report_path=args.step264_report,
        step263_report_path=args.step263_report,
        step262_report_path=args.step262_report,
        step261_report_path=args.step261_report,
        step260_report_path=args.step260_report,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        approval_decision=args.approval_decision,
        approver=args.approver,
        approval_rationale=args.approval_rationale,
        approval_timestamp_utc=args.approval_timestamp_utc,
        review_decision=args.review_decision,
        reviewer=args.reviewer,
        review_rationale=args.review_rationale,
        review_timestamp_utc=args.review_timestamp_utc,
        operator_label=args.operator_label,
        notes=args.notes,
        timestamp_utc=args.timestamp_utc,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    packet = report["apply_dry_run_packet"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "apply_dry_run_id": packet["apply_dry_run_id"],
        "dry_run_status": packet["dry_run"]["dry_run_status"],
        "production_candidate_profile": packet["candidate"]["production_candidate_profile"],
        "diff_changed_count": packet["diff"]["changed_count"],
        "mutation_plan_write_enabled": packet["mutation_plan"]["write_enabled"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
