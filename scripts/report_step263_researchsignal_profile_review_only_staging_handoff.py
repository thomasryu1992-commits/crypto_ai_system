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
from crypto_ai_system.research.research_signal_profile_staging_handoff import (
    STEP263_PROFILE_STAGING_HANDOFF_VERSION,
    apply_step263_staging_handoff_disabled_stub,
    build_step263_review_only_staging_handoff_packet,
    validate_step263_staging_handoff_packet,
)
from scripts.report_step262_researchsignal_profile_approval_intake_validator import build_report as build_step262_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step262_report(
    root: Path,
    *,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    rationale: str = "Step263 default review-only staging handoff run.",
    timestamp_utc: str | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step262_report_path:
        p = Path(step262_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step262_researchsignal_profile_approval_intake_validator_report.json",
        root / "storage/latest/step262_researchsignal_profile_approval_intake_validator_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            return data, str(path.relative_to(root) if path.is_relative_to(root) else path)
    return (
        build_step262_report(
            root,
            step261_report_path=step261_report_path,
            step260_report_path=step260_report_path,
            matrix_path=matrix_path,
            max_rows=max_rows,
            approval_decision=approval_decision,
            approver=approver,
            rationale=rationale,
            timestamp_utc=timestamp_utc,
        ),
        "rebuilt_step262_report",
    )


def build_report(
    root: Path,
    *,
    step262_report_path: str | None = None,
    step261_report_path: str | None = None,
    step260_report_path: str | None = None,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    approval_decision: str = "REQUEST_MORE_DATA",
    approver: str = "manual_reviewer",
    rationale: str = "Step263 default review-only staging handoff run.",
    timestamp_utc: str | None = None,
    operator_label: str = "manual_reviewer",
    notes: str = "",
) -> dict[str, Any]:
    cfg = load_config(root)
    step262_report, step262_report_source = load_or_build_step262_report(
        root,
        step262_report_path=step262_report_path,
        step261_report_path=step261_report_path,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
        approval_decision=approval_decision,
        approver=approver,
        rationale=rationale,
        timestamp_utc=timestamp_utc,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    handoff_packet = build_step263_review_only_staging_handoff_packet(
        step262_report,
        cfg,
        operator_label=operator_label,
        notes=notes,
        timestamp_utc=timestamp_utc,
    )
    handoff_validation = validate_step263_staging_handoff_packet(handoff_packet)
    apply_stub = apply_step263_staging_handoff_disabled_stub(handoff_packet, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})

    report = {
        "step": 263,
        "status": "completed" if handoff_validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_review_only_staging_handoff_pre_apply_checklist",
        "version": STEP263_PROFILE_STAGING_HANDOFF_VERSION,
        "step262_report_source": step262_report_source,
        "staging_handoff_packet": handoff_packet,
        "staging_handoff_validation": handoff_validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "staging_handoff_policy": {
            "staging_handoff_created": True,
            "pre_apply_checklist_created": True,
            "ready_for_pre_apply_review": handoff_packet["handoff"]["ready_for_pre_apply_review"],
            "approve_for_review_only_staging_is_not_runtime_apply": True,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_deferred": True,
        },
        "safety_boundaries": handoff_packet["safety_boundaries"],
        "next_step": {
            "name": "Step264",
            "goal": "Validate a manual pre-apply review record for the Step263 staging handoff, while keeping score-weight mutation disabled.",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step263 ResearchSignal profile review-only staging handoff report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step262-report", default=None, help="Optional Step262 report JSON path")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path when rebuilding Step262")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261/262")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260/261/262")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--approver", default="manual_reviewer")
    parser.add_argument("--rationale", default="Step263 default review-only staging handoff run.")
    parser.add_argument("--timestamp-utc", default=None)
    parser.add_argument("--operator-label", default="manual_reviewer")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default="data/reports/step263_researchsignal_profile_review_only_staging_handoff_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step263_researchsignal_profile_review_only_staging_handoff_latest.json")
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
        step262_report_path=args.step262_report,
        step261_report_path=args.step261_report,
        step260_report_path=args.step260_report,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        approval_decision=args.approval_decision,
        approver=args.approver,
        rationale=args.rationale,
        timestamp_utc=args.timestamp_utc,
        operator_label=args.operator_label,
        notes=args.notes,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")

    packet = report["staging_handoff_packet"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "staging_handoff_id": packet["staging_handoff_id"],
        "approval_packet_id": packet["source"]["approval_packet_id"],
        "handoff_status": packet["handoff"]["handoff_status"],
        "ready_for_pre_apply_review": packet["handoff"]["ready_for_pre_apply_review"],
        "production_candidate_profile": packet["candidate"]["production_candidate_profile"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
