from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from crypto_ai_system.governance.pre_executor_review import (
    run_pre_executor_review_chain,
)
from crypto_ai_system.governance.signed_testnet_execution_preparation import (
    run_signed_testnet_execution_preparation_chain,
)

MODE_PREPARE_TEMPLATE = "prepare-template"
MODE_VALIDATE_SUBMISSION = "validate-submission"

OPERATOR_TEMPLATE_RELATIVE_PATH = (
    "storage/latest/"
    "operator_decision_intake_template_review_only.json"
)

OPERATOR_SUBMISSION_RELATIVE_PATH = (
    "storage/manual_operator_decision/"
    "operator_decision_intake_submission.json"
)


def _load_json_object(
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"Expected a JSON object: {path}"
        )

    return dict(
        payload
    )


def _build_summary(
    *,
    mode: str,
    project_root: Path,
    phase7_result: Mapping[
        str,
        Any,
    ],
    phase8_result: Mapping[
        str,
        Any,
    ],
) -> dict[str, Any]:
    phase7 = dict(
        phase7_result.get(
            "report"
        )
        or {}
    )

    phase7_artifacts = dict(
        phase7_result.get(
            "legacy_outputs"
        )
        or {}
    )

    phase8 = dict(
        phase8_result.get(
            "report"
        )
        or {}
    )

    phase9 = dict(
        phase8_result.get(
            "phase9_single_order_approval_review_packet"
        )
        or {}
    )

    intake_template = dict(
        phase7_artifacts.get(
            "operator_decision_intake_template"
        )
        or {}
    )

    return {
        "mode": mode,
        "review_only": True,
        "canonical_handoff_runner": True,
        "operator_submission_written_automatically": False,
        "operator_template_path": str(
            (
                project_root
                / OPERATOR_TEMPLATE_RELATIVE_PATH
            ).resolve()
        ),
        "operator_submission_target_path": str(
            (
                project_root
                / OPERATOR_SUBMISSION_RELATIVE_PATH
            ).resolve()
        ),
        "phase7_status": phase7.get(
            "status"
        ),
        "phase7_state": phase7.get(
            "pre_executor_review_state"
        ),
        "phase7_operator_decision_intake_validated": (
            phase7.get(
                "operator_decision_intake_validated"
            )
            is True
        ),
        "phase7_actual_operator_decision_recorded": (
            phase7.get(
                "actual_operator_decision_recorded"
            )
            is True
        ),
        "phase7_final_pre_executor_review_ready": (
            phase7.get(
                "final_pre_executor_review_ready"
            )
            is True
        ),
        "phase7_blockers": (
            phase7.get(
                "blockers"
            )
            or []
        ),
        "phase7_next_action": (
            phase7.get(
                "next_action"
            )
        ),
        "source_phase7_14_report_id": (
            intake_template.get(
                "source_phase7_14_report_id"
            )
        ),
        "source_phase7_14_report_hash": (
            intake_template.get(
                "source_phase7_14_report_hash"
            )
        ),
        "source_stage_transition_review_id": (
            intake_template.get(
                "source_stage_transition_review_id"
            )
        ),
        "source_stage_transition_review_hash": (
            intake_template.get(
                "source_stage_transition_review_hash"
            )
        ),
        "phase8_status": phase8.get(
            "status"
        ),
        "phase8_fresh_runtime_evidence_validated": (
            phase8.get(
                "phase8_fresh_runtime_evidence_validated"
            )
            is True
        ),
        "phase8_blockers": (
            phase8.get(
                "blockers"
            )
            or []
        ),
        "phase8_next_action": (
            phase8.get(
                "next_action"
            )
        ),
        "phase9_status": phase9.get(
            "status"
        ),
        "phase9_review_packet_ready": (
            phase9.get(
                "phase9_single_order_approval_review_packet_ready"
            )
            is True
        ),
        "phase9_blockers": (
            phase9.get(
                "blockers"
            )
            or []
        ),
        "phase9_next_action": (
            phase9.get(
                "next_action"
            )
        ),
        "actual_phase9_approval_created": False,
        "phase9_order_submission_permission_granted": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _run_canonical_handoff(
    *,
    project_root: Path,
    mode: str,
    operator_submission_file: Path | None,
) -> dict[str, Any]:
    if (
        mode
        == MODE_PREPARE_TEMPLATE
    ):
        if (
            operator_submission_file
            is not None
        ):
            raise ValueError(
                "--operator-submission-file is only valid "
                "with --mode validate-submission"
            )

        phase7_result = (
            run_pre_executor_review_chain(
                project_root=(
                    project_root
                ),
                run_stage_transition_first=True,
            )
        )

    elif (
        mode
        == MODE_VALIDATE_SUBMISSION
    ):
        if (
            operator_submission_file
            is None
        ):
            raise ValueError(
                "--operator-submission-file is required "
                "with --mode validate-submission"
            )

        submission = (
            _load_json_object(
                operator_submission_file
            )
        )

        phase7_result = (
            run_pre_executor_review_chain(
                project_root=(
                    project_root
                ),
                run_stage_transition_first=False,
                submission_override=(
                    submission
                ),
            )
        )

    else:
        raise ValueError(
            f"Unsupported mode: {mode}"
        )

    phase8_result = (
        run_signed_testnet_execution_preparation_chain(
            project_root=(
                project_root
            )
        )
    )

    return {
        "phase7": (
            phase7_result
        ),
        "phase8": (
            phase8_result
        ),
        "summary": (
            _build_summary(
                mode=mode,
                project_root=(
                    project_root
                ),
                phase7_result=(
                    phase7_result
                ),
                phase8_result=(
                    phase8_result
                ),
            )
        ),
    }


def main(
    argv: Sequence[
        str
    ] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or validate the canonical review-only "
            "Phase 7.14 -> Phase 9 single-order handoff."
        )
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help=(
            "Repository root containing config and storage directories."
        ),
    )

    parser.add_argument(
        "--mode",
        choices=(
            MODE_PREPARE_TEMPLATE,
            MODE_VALIDATE_SUBMISSION,
        ),
        default=(
            MODE_PREPARE_TEMPLATE
        ),
        help=(
            "prepare-template refreshes Phase 7.14 sources and writes "
            "the latest review template. validate-submission preserves "
            "those source IDs/hashes and validates one manual submission."
        ),
    )

    parser.add_argument(
        "--operator-submission-file",
        type=Path,
        default=None,
        help=(
            "Manual metadata-only operator submission JSON. "
            "Required only for validate-submission."
        ),
    )

    parser.add_argument(
        "--strict-phase9-review-ready",
        action="store_true",
        help=(
            "Return exit code 2 unless the Phase 9 review packet is ready. "
            "This never grants approval or order permission."
        ),
    )

    args = parser.parse_args(
        argv
    )

    project_root = (
        args.project_root
        .resolve()
    )

    submission_file = (
        args.operator_submission_file
        .resolve()
        if (
            args.operator_submission_file
            is not None
        )
        else None
    )

    result = (
        _run_canonical_handoff(
            project_root=(
                project_root
            ),
            mode=(
                args.mode
            ),
            operator_submission_file=(
                submission_file
            ),
        )
    )

    summary = dict(
        result[
            "summary"
        ]
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    if (
        args.strict_phase9_review_ready
        and summary.get(
            "phase9_review_packet_ready"
        )
        is not True
    ):
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
