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
from crypto_ai_system.research.research_signal_profile_pre_apply_review import (
    STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
    apply_step264_pre_apply_review_disabled_stub,
    build_step264_pre_apply_review_record,
    validate_step264_pre_apply_review_record,
)
from scripts.report_step263_researchsignal_profile_review_only_staging_handoff import build_report as build_step263_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step263_report(
    root: Path,
    *,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    approval_rationale: str = "Step264 default upstream approval-intake rebuild.",
    approval_timestamp_utc: str | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step263_report_path:
        p = Path(step263_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step263_researchsignal_profile_review_only_staging_handoff_report.json",
        root / "storage/latest/step263_researchsignal_profile_review_only_staging_handoff_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            try:
                return data, str(path.relative_to(root))
            except ValueError:
                return data, str(path)
    return (
        build_step263_report(
            root,
            step262_report_path=step262_report_path,
            step261_report_path=step261_report_path,
            step260_report_path=step260_report_path,
            matrix_path=matrix_path,
            max_rows=max_rows,
            approval_decision=approval_decision,
            approver=approver,
            rationale=approval_rationale,
            timestamp_utc=approval_timestamp_utc,
        ),
        "rebuilt_step263_report",
    )


def build_report(
    root: Path,
    *,
    step263_report_path: str | None = None,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    approval_rationale: str = "Step264 default upstream approval-intake rebuild.",
    approval_timestamp_utc: str | None = None,
    review_decision: str = "REQUEST_MORE_DATA",
    reviewer: str = "manual_pre_apply_reviewer",
    rationale: str = "Step264 default manual pre-apply review validator run.",
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    step263_report, step263_report_source = load_or_build_step263_report(
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
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    pre_apply_record = build_step264_pre_apply_review_record(
        step263_report,
        cfg,
        review_decision=review_decision,
        reviewer=reviewer,
        rationale=rationale,
        timestamp_utc=timestamp_utc,
    )
    record_validation = validate_step264_pre_apply_review_record(pre_apply_record)
    apply_stub = apply_step264_pre_apply_review_disabled_stub(pre_apply_record, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})

    review = pre_apply_record["pre_apply_review_record"]
    report = {
        "step": 264,
        "status": "completed" if record_validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_manual_pre_apply_review_record_validator_disabled_apply",
        "version": STEP264_PROFILE_PRE_APPLY_REVIEW_VERSION,
        "step263_report_source": step263_report_source,
        "pre_apply_review_record": pre_apply_record,
        "pre_apply_review_validation": record_validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "pre_apply_review_policy": {
            "pre_apply_review_record_created": True,
            "review_decision": review["review_decision"],
            "canonical_review_decision": review["canonical_review_decision"],
            "record_status": review["record_status"],
            "ready_is_not_runtime_apply": True,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_deferred": True,
        },
        "safety_boundaries": pre_apply_record["safety_boundaries"],
        "next_step": {
            "name": "Step265",
            "goal": "Create a disabled apply-candidate dry-run packet from a READY Step264 record, while keeping score_weights mutation disabled.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step264 ResearchSignal profile manual pre-apply review validator report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step263-report", default=None, help="Optional Step263 report JSON path")
    parser.add_argument("--step262-report", default=None, help="Optional Step262 report JSON path when rebuilding Step263")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path when rebuilding Step262/263")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261/262/263")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260+ chain")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--approver", default="manual_reviewer")
    parser.add_argument("--approval-rationale", default="Step264 default upstream approval-intake rebuild.")
    parser.add_argument("--approval-timestamp-utc", default=None)
    parser.add_argument("--review-decision", default="REQUEST_MORE_DATA", choices=["READY", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--reviewer", default="manual_pre_apply_reviewer")
    parser.add_argument("--rationale", default="Step264 default manual pre-apply review validator run.")
    parser.add_argument("--timestamp-utc", default=None)
    parser.add_argument("--output", default="data/reports/step264_researchsignal_profile_pre_apply_review_validator_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step264_researchsignal_profile_pre_apply_review_validator_latest.json")
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
        rationale=args.rationale,
        timestamp_utc=args.timestamp_utc,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    record = report["pre_apply_review_record"]
    review = record["pre_apply_review_record"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "staging_handoff_id": record["staging_handoff_id"],
        "approval_packet_id": record["approval_packet_id"],
        "review_decision": review["review_decision"],
        "record_status": review["record_status"],
        "production_candidate_profile": record["production_candidate_profile"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
