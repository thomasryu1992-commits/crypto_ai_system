from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_profile_settings_write_preview import (
    STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
    apply_step267_disabled_settings_write_preview_stub,
    build_step267_disabled_settings_write_preview_packet,
    validate_step267_disabled_settings_write_preview_packet,
)
from scripts.report_step266_researchsignal_profile_final_apply_approval_validator import build_report as build_step266_report


def _read_json_if_available(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_or_build_step266_report(
    root: Path,
    *,
    step266_report_path: str | None = None,
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
    upstream_approval_rationale: str = "Step267 default upstream approval-intake rebuild.",
    upstream_approval_timestamp_utc: str | None = None,
    upstream_review_decision: str = "REQUEST_MORE_DATA",
    upstream_reviewer: str = "manual_pre_apply_reviewer",
    upstream_review_rationale: str = "Step267 default upstream pre-apply review rebuild.",
    upstream_review_timestamp_utc: str | None = None,
    dry_run_operator_label: str = "manual_apply_dry_run_reviewer",
    dry_run_notes: str = "Step267 default upstream disabled dry-run rebuild.",
    dry_run_timestamp_utc: str | None = None,
    final_approval_decision: str = "REQUEST_MORE_DATA",
    final_approver: str = "manual_final_apply_reviewer",
    final_rationale: str = "Step267 default final approval requires ready disabled dry-run packet.",
    final_timestamp_utc: str | None = None,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if step266_report_path:
        p = Path(step266_report_path)
        candidates.append(p if p.is_absolute() else root / p)
    candidates.extend([
        root / "data/reports/step266_researchsignal_profile_final_apply_approval_validator_report.json",
        root / "storage/latest/step266_researchsignal_profile_final_apply_approval_validator_latest.json",
    ])
    for path in candidates:
        data = _read_json_if_available(path)
        if data is not None:
            try:
                return data, str(path.relative_to(root))
            except ValueError:
                return data, str(path)
    return (
        build_step266_report(
            root,
            step265_report_path=step265_report_path,
            step264_report_path=step264_report_path,
            step263_report_path=step263_report_path,
            step262_report_path=step262_report_path,
            step261_report_path=step261_report_path,
            step260_report_path=step260_report_path,
            matrix_path=matrix_path,
            max_rows=max_rows,
            upstream_approval_decision=upstream_approval_decision,
            upstream_approver=upstream_approver,
            upstream_approval_rationale=upstream_approval_rationale,
            upstream_approval_timestamp_utc=upstream_approval_timestamp_utc,
            upstream_review_decision=upstream_review_decision,
            upstream_reviewer=upstream_reviewer,
            upstream_review_rationale=upstream_review_rationale,
            upstream_review_timestamp_utc=upstream_review_timestamp_utc,
            dry_run_operator_label=dry_run_operator_label,
            dry_run_notes=dry_run_notes,
            dry_run_timestamp_utc=dry_run_timestamp_utc,
            final_approval_decision=final_approval_decision,
            final_approver=final_approver,
            final_rationale=final_rationale,
            final_timestamp_utc=final_timestamp_utc,
        ),
        "rebuilt_step266_report",
    )


def build_report(
    root: Path,
    *,
    step266_report_path: str | None = None,
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
    upstream_approval_rationale: str = "Step267 default upstream approval-intake rebuild.",
    upstream_approval_timestamp_utc: str | None = None,
    upstream_review_decision: str = "REQUEST_MORE_DATA",
    upstream_reviewer: str = "manual_pre_apply_reviewer",
    upstream_review_rationale: str = "Step267 default upstream pre-apply review rebuild.",
    upstream_review_timestamp_utc: str | None = None,
    dry_run_operator_label: str = "manual_apply_dry_run_reviewer",
    dry_run_notes: str = "Step267 default upstream disabled dry-run rebuild.",
    dry_run_timestamp_utc: str | None = None,
    final_approval_decision: str = "REQUEST_MORE_DATA",
    final_approver: str = "manual_final_apply_reviewer",
    final_rationale: str = "Step267 default final approval requires ready disabled dry-run packet.",
    final_timestamp_utc: str | None = None,
    preview_operator_label: str = "manual_settings_write_preview_reviewer",
    preview_notes: str = "Step267 default settings-write preview requires approved disabled dry-run final record.",
    preview_timestamp_utc: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    step266_report, step266_report_source = load_or_build_step266_report(
        root,
        step266_report_path=step266_report_path,
        step265_report_path=step265_report_path,
        step264_report_path=step264_report_path,
        step263_report_path=step263_report_path,
        step262_report_path=step262_report_path,
        step261_report_path=step261_report_path,
        step260_report_path=step260_report_path,
        matrix_path=matrix_path,
        max_rows=max_rows,
        upstream_approval_decision=upstream_approval_decision,
        upstream_approver=upstream_approver,
        upstream_approval_rationale=upstream_approval_rationale,
        upstream_approval_timestamp_utc=upstream_approval_timestamp_utc,
        upstream_review_decision=upstream_review_decision,
        upstream_reviewer=upstream_reviewer,
        upstream_review_rationale=upstream_review_rationale,
        upstream_review_timestamp_utc=upstream_review_timestamp_utc,
        dry_run_operator_label=dry_run_operator_label,
        dry_run_notes=dry_run_notes,
        dry_run_timestamp_utc=dry_run_timestamp_utc,
        final_approval_decision=final_approval_decision,
        final_approver=final_approver,
        final_rationale=final_rationale,
        final_timestamp_utc=final_timestamp_utc,
    )
    weights_before = dict(cfg.get("research.score_weights", {}) or {})
    packet = build_step267_disabled_settings_write_preview_packet(
        step266_report,
        cfg,
        operator_label=preview_operator_label,
        notes=preview_notes,
        timestamp_utc=preview_timestamp_utc,
    )
    validation = validate_step267_disabled_settings_write_preview_packet(packet)
    apply_stub = apply_step267_disabled_settings_write_preview_stub(packet, cfg)
    weights_after = dict(cfg.get("research.score_weights", {}) or {})
    preview = packet["preview"]
    artifact = packet["settings_yaml_diff_artifact"]

    report = {
        "step": 267,
        "status": "completed" if validation["valid"] else "failed_validation",
        "scope": "researchsignal_v2_profile_disabled_settings_write_preview_export",
        "version": STEP267_PROFILE_SETTINGS_WRITE_PREVIEW_VERSION,
        "step266_report_source": step266_report_source,
        "settings_write_preview_packet": packet,
        "settings_write_preview_validation": validation,
        "application_stub_result": apply_stub,
        "runtime_score_weights_before": weights_before,
        "runtime_score_weights_after": weights_after,
        "runtime_score_weights_unchanged": weights_before == weights_after,
        "settings_write_preview_policy": {
            "preview_packet_created": True,
            "preview_status": preview["preview_status"],
            "ready_for_disabled_settings_write_preview": preview["ready_for_disabled_settings_write_preview"],
            "production_candidate_profile": packet["production_candidate_profile"],
            "settings_yaml_diff_rendered": bool(artifact.get("unified_diff") is not None),
            "candidate_settings_yaml_rendered": bool(artifact.get("candidate_settings_yaml")),
            "settings_write_enabled": False,
            "config_write_enabled": False,
            "runtime_score_weight_mutation_allowed": False,
            "settings_score_weight_mutation_allowed": False,
            "apply_stage_still_deferred": True,
        },
        "safety_boundaries": packet["safety_boundaries"],
        "next_step": {
            "name": "Step268",
            "goal": "Add a disabled settings-write export integrity validator before any future apply path while keeping config writes blocked.",
        },
    }
    return report


def _write_outputs(report: dict[str, Any], output: Path, latest_output: Path, diff_output: Path, candidate_yaml_output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    diff_output.parent.mkdir(parents=True, exist_ok=True)
    candidate_yaml_output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    output.write_text(rendered, encoding="utf-8")
    latest_output.write_text(rendered, encoding="utf-8")
    artifact = report["settings_write_preview_packet"]["settings_yaml_diff_artifact"]
    diff_output.write_text(str(artifact.get("unified_diff") or ""), encoding="utf-8")
    candidate_yaml_output.write_text(str(artifact.get("candidate_settings_yaml") or ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step267 disabled settings-write preview/export packet report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--step266-report", default=None, help="Optional Step266 report JSON path")
    parser.add_argument("--step265-report", default=None, help="Optional Step265 report JSON path when rebuilding Step266")
    parser.add_argument("--step264-report", default=None, help="Optional Step264 report JSON path when rebuilding Step265+")
    parser.add_argument("--step263-report", default=None, help="Optional Step263 report JSON path when rebuilding Step264+")
    parser.add_argument("--step262-report", default=None, help="Optional Step262 report JSON path when rebuilding Step263+")
    parser.add_argument("--step261-report", default=None, help="Optional Step261 report JSON path when rebuilding Step262+")
    parser.add_argument("--step260-report", default=None, help="Optional Step260 report JSON path when rebuilding Step261+")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path for rebuilding Step260+ chain")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap when rebuilding reports")
    parser.add_argument("--upstream-approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_FOR_REVIEW_ONLY_STAGING", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--upstream-approver", default="manual_reviewer")
    parser.add_argument("--upstream-approval-rationale", default="Step267 default upstream approval-intake rebuild.")
    parser.add_argument("--upstream-approval-timestamp-utc", default=None)
    parser.add_argument("--upstream-review-decision", default="REQUEST_MORE_DATA", choices=["READY", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--upstream-reviewer", default="manual_pre_apply_reviewer")
    parser.add_argument("--upstream-review-rationale", default="Step267 default upstream pre-apply review rebuild.")
    parser.add_argument("--upstream-review-timestamp-utc", default=None)
    parser.add_argument("--dry-run-operator-label", default="manual_apply_dry_run_reviewer")
    parser.add_argument("--dry-run-notes", default="Step267 default upstream disabled dry-run rebuild.")
    parser.add_argument("--dry-run-timestamp-utc", default=None)
    parser.add_argument("--final-approval-decision", default="REQUEST_MORE_DATA", choices=["APPROVE_DRY_RUN", "REJECT", "REQUEST_MORE_DATA"])
    parser.add_argument("--final-approver", default="manual_final_apply_reviewer")
    parser.add_argument("--final-rationale", default="Step267 default final approval requires ready disabled dry-run packet.")
    parser.add_argument("--final-timestamp-utc", default=None)
    parser.add_argument("--preview-operator-label", default="manual_settings_write_preview_reviewer")
    parser.add_argument("--preview-notes", default="Step267 default settings-write preview requires approved disabled dry-run final record.")
    parser.add_argument("--preview-timestamp-utc", default=None)
    parser.add_argument("--output", default="data/reports/step267_researchsignal_profile_disabled_settings_write_preview_report.json")
    parser.add_argument("--latest-output", default="storage/latest/step267_researchsignal_profile_disabled_settings_write_preview_latest.json")
    parser.add_argument("--diff-output", default="data/reports/step267_settings_write_preview.diff")
    parser.add_argument("--candidate-yaml-output", default="data/reports/step267_settings_write_preview_candidate_settings.yaml")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    latest_output = Path(args.latest_output)
    diff_output = Path(args.diff_output)
    candidate_yaml_output = Path(args.candidate_yaml_output)
    if not output.is_absolute():
        output = root / output
    if not latest_output.is_absolute():
        latest_output = root / latest_output
    if not diff_output.is_absolute():
        diff_output = root / diff_output
    if not candidate_yaml_output.is_absolute():
        candidate_yaml_output = root / candidate_yaml_output

    report = build_report(
        root,
        step266_report_path=args.step266_report,
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
        preview_operator_label=args.preview_operator_label,
        preview_notes=args.preview_notes,
        preview_timestamp_utc=args.preview_timestamp_utc,
    )
    _write_outputs(report, output, latest_output, diff_output, candidate_yaml_output)
    packet = report["settings_write_preview_packet"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "latest_output": str(latest_output),
        "diff_output": str(diff_output),
        "candidate_yaml_output": str(candidate_yaml_output),
        "settings_write_preview_id": packet["settings_write_preview_id"],
        "preview_status": packet["preview"]["preview_status"],
        "production_candidate_profile": packet["production_candidate_profile"],
        "settings_write_enabled": report["settings_write_preview_policy"]["settings_write_enabled"],
        "config_write_enabled": report["settings_write_preview_policy"]["config_write_enabled"],
        "runtime_score_weights_unchanged": report["runtime_score_weights_unchanged"],
        "application_stub_status": report["application_stub_result"]["status"],
        "external_order_submission_performed": report["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
