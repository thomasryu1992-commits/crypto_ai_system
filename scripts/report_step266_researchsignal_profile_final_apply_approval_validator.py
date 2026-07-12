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
from crypto_ai_system.research.research_signal_profile_final_apply_approval import (
    STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
    apply_step266_final_manual_apply_approval_disabled_stub,
    build_step266_final_manual_apply_approval_record,
    validate_step266_final_manual_apply_approval_record,
)
from scripts.report_step265_researchsignal_profile_disabled_apply_dry_run import build_report as build_step265_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step265_report(
    root: Path,
    *,
    step265_report_path: str | None = None,
    step264_report_path: str | None = None,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    approval_rationale: str = "Step266 default upstream approval-intake rebuild.",
    approval_timestamp_utc: str | None = None,
    review_decision: str = "REQUEST_MORE_DATA",
    reviewer: str = "manual_pre_apply_reviewer",
    review_rationale: str = "Step266 default upstream pre-apply review rebuild.",
    review_timestamp_utc: str | None = None,
    dry_run_operator_label: str = "manual_apply_dry_run_reviewer",
    dry_run_notes: str = "Step266 default upstream disabled dry-run rebuild.",
    dry_run_timestamp_utc: str | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step265_report_path:
        p = Path(step265_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step265_researchsignal_profile_disabled_apply_dry_run_report.json",
        root / "storage/latest/step265_researchsignal_profile_disabled_apply_dry_run_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            try:
                return data, str(path.relative_to(root))
            except ValueError:
                return data, str(path)
    return (
        build_step265_report(
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
            operator_label=dry_run_operator_label,
            notes=dry_run_notes,
            timestamp_utc=dry_run_timestamp_utc,
        ),
        "rebuilt_step265_report",
    )


def build_report(
    root: Path,
    *,
    step265_report_path: str | None = None,
    step264_report_path: str | None = None,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    upstream_approval_decision: str = "REQUEST_MORE_DATA",
    upstream_approver: str = "manual_reviewer",
    upstream_approval_rationale: str = "Step266 default upstream approval-intake rebuild.",
    upstream_approval_timestamp_utc: str | None = None,
    upstream_review_decision: str = "REQUEST_MORE_DATA",
    upstream_reviewer: str = "manual_pre_apply_reviewer",
    upstream_review_rationale: str = "Step266 default upstream pre-apply review rebuild.",
    upstream_review_timestamp_utc: str | None = None,
    dry_run_operator_label: str = "manual_apply_dry_run_reviewer",
    dry_run_notes: str = "Step266 default upstream disabled dry-run rebuild.",
    dry_run_timestamp_utc: str | None = None,
    final_approval_decision: str = "REQUEST_MORE_DATA",
    final_approver: str = "manual_final_apply_reviewer",
    final_rationale: str = "Step266 default final approval requires ready disabled dry-run packet.",
    final_timestamp_utc: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    step265_report, step265_report_source = load_or_build_step265_report(
        root,
        step265_report_path=step265_report_path,
        step264_report_path=step264_report_path,
        step263_report_path=step263_report_path,
        step262_report_path=step262_report_path,
        step261_report_path=step261_report_path,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
        approval_decision=upstream_approval_decision,
        approver=upstream_approver,
        approval_rationale=upstream_approval_rationale,
        approval_timestamp_utc=upstream_approval_timestamp_utc,
        review_decision=upstream_review_decision,
        reviewer=upstream_reviewer,
        review_rationale=upstream_review_rationale,
        review_timestamp_utc=upstream_review_timestamp_utc,
        dry_run_operator_label=dry_run_operator_label,
        dry_run_notes=dry_run_notes,
        dry_run_timestamp_utc=dry_run_timestamp_utc,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    record = build_step266_final_manual_apply_approval_record(
        step265_report,
        cfg,
        approval_decision=final_approval_decision,
        approver=final_approver,
        rationale=final_rationale,
        timestamp_utc=final_timestamp_utc,
    )
    validation = validate_step266_final_manual_apply_approval_record(record)
    apply_stub = apply_step266_final_manual_apply_approval_disabled_stub(record, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})
    final_record = record["final_apply_approval_record"]

    report = {
        "step": 266,
        "status": "completed" if validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_final_manual_apply_approval_validator_disabled_apply",
        "version": STEP266_PROFILE_FINAL_APPLY_APPROVAL_VERSION,
        "step265_report_source": step265_report_source,
        "final_apply_approval_record": record,
        "final_apply_approval_validation": validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "final_apply_approval_policy": {
            "final_apply_record_created": True,
            "approval_decision": final_record["approval_decision"],
            "record_status": final_record["record_status"],
            "disabled_dry_run_final_approval_recorded": record["decision_effect"]["disabled_dry_run_final_approval_recorded"],
            "candidate_profile_applied": False,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_still_deferred": True,
        },
        "safety_boundaries": record["safety_boundaries"],
        "next_step": {
            "name": "Step267",
            "goal": "Add a disabled settings-write preview/export packet for the approved dry-run path while keeping score_weights mutation blocked.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step266 ResearchSignal final manual apply approval validator report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step265-report", default=None, help="Optional Step265 report JSON path")
    parser.add_argument("--step264-report", default=None, help="Optional Step264 report JSON path when rebuilding Step265")
    parser.add_argument("--step263-report", default=None, help="Optional Step263 report JSON path when rebuilding Step264+")
    parser.add_argument("--step262-report", default=None, help="Optional Step262 report JSON path when rebuilding Step263+")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path when rebuilding Step262+")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261+")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260+ chain")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--upstream-approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--upstream-approver", default="manual_reviewer")
    parser.add_argument("--upstream-approval-rationale", default="Step266 default upstream approval-intake rebuild.")
    parser.add_argument("--upstream-approval-timestamp-utc", default=None)
    parser.add_argument("--upstream-review-decision", default="REQUEST_MORE_DATA", choices=["READY", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--upstream-reviewer", default="manual_pre_apply_reviewer")
    parser.add_argument("--upstream-review-rationale", default="Step266 default upstream pre-apply review rebuild.")
    parser.add_argument("--upstream-review-timestamp-utc", default=None)
    parser.add_argument("--dry-run-operator-label", default="manual_apply_dry_run_reviewer")
    parser.add_argument("--dry-run-notes", default="Step266 default upstream disabled dry-run rebuild.")
    parser.add_argument("--dry-run-timestamp-utc", default=None)
    parser.add_argument("--final-approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_DRY_RUN", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--final-approver", default="manual_final_apply_reviewer")
    parser.add_argument("--final-rationale", default="Step266 default final approval requires ready disabled dry-run packet.")
    parser.add_argument("--final-timestamp-utc", default=None)
    parser.add_argument("--output", default="data/reports/step266_researchsignal_profile_final_apply_approval_validator_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step266_researchsignal_profile_final_apply_approval_validator_latest.json")
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
        step265_report_path=args.step265_report,
        step264_report_path=args.step264_report,
        step263_report_path=args.step263_report,
        step262_report_path=args.step262_report,
        step261_report_path=args.step261_report,
        step260_report_path=args.step260_report,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        upstream_approval_decision=args.upstream_approval_decision,
        upstream_approver=args.upstream_approver,
        upstream_approval_rationale=args.upstream_approval_rationale,
        upstream_approval_timestamp_utc=args.upstream_approval_timestamp_utc,
        upstream_review_decision=args.upstream_review_decision,
        upstream_reviewer=args.upstream_reviewer,
        upstream_review_rationale=args.upstream_review_rationale,
        upstream_review_timestamp_utc=args.upstream_review_timestamp_utc,
        dry_run_operator_label=args.dry_run_operator_label,
        dry_run_notes=args.dry_run_notes,
        dry_run_timestamp_utc=args.dry_run_timestamp_utc,
        final_approval_decision=args.final_approval_decision,
        final_approver=args.final_approver,
        final_rationale=args.final_rationale,
        final_timestamp_utc=args.final_timestamp_utc,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    record = report["final_apply_approval_record"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "final_apply_approval_id": record["final_apply_approval_id"],
        "record_status": record["final_apply_approval_record"]["record_status"],
        "approval_decision": record["final_apply_approval_record"]["approval_decision"],
        "production_candidate_profile": record["production_candidate_profile"],
        "candidate_profile_applied": report["final_apply_approval_policy"]["candidate_profile_applied"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
