from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import bootstrap

ROOT = bootstrap()

from crypto_ai_system.config import load_config
from crypto_ai_system.research.research_signal_calibration import (
    STEP260_CALIBRATION_REVIEW_VERSION,
    build_step260_profile_review,
)
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix


STORED_MATRIX_CANDIDATES = [
    "storage/features/research_feature_matrix_backtest.csv",
    "storage/features/research_feature_matrix_live.csv",
    "storage/features/research_feature_matrix.csv",
]


def _read_csv_if_available(path: Path) -> pd.DataFrame | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        frame = pd.read_csv(path)
    except Exception:
        return None
    if frame.empty:
        return None
    return frame


def load_step260_matrix(root: Path, matrix_path: str | None = None) -> tuple[pd.DataFrame, str, str]:
    """Load an explicit/stored Feature Store matrix or a synthetic fallback.

    Explicit and stored matrices are treated as reviewable production-candidate
    inputs. Synthetic fallback is useful for CI and shape validation only; it is
    never eligible for production profile candidate selection.
    """
    if matrix_path:
        explicit = Path(matrix_path)
        explicit = explicit if explicit.is_absolute() else root / explicit
        frame = _read_csv_if_available(explicit)
        if frame is not None:
            source = str(explicit.relative_to(root) if explicit.is_relative_to(root) else explicit)
            return frame, source, "explicit_feature_store_matrix"

    for rel in STORED_MATRIX_CANDIDATES:
        path = root / rel
        frame = _read_csv_if_available(path)
        if frame is not None:
            return frame, rel, "stored_feature_store_matrix"

    return _synthetic_calibration_matrix(), "synthetic_step260_review_only_calibration_matrix", "synthetic_fallback_matrix"


def build_report(
    root: Path,
    *,
    matrix_path: str | None = None,
    max_rows: int | None = None,
    criteria_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(root)
    matrix, matrix_source, matrix_source_type = load_step260_matrix(root, matrix_path)
    review = build_step260_profile_review(
        matrix,
        cfg,
        matrix_source=matrix_source,
        matrix_source_type=matrix_source_type,
        max_rows=max_rows,
        criteria_overrides=criteria_overrides,
    )
    report = {
        "step": 260,
        "status": "completed",
        "scope": "researchsignal_v2_profile_review_only_calibration_against_feature_store_matrix",
        "version": STEP260_CALIBRATION_REVIEW_VERSION,
        "review": review,
        "production_candidate_policy": {
            "candidate_selection_requires_real_feature_store_matrix": True,
            "synthetic_fallback_can_select_candidate": False,
            "selected_profile_auto_apply_allowed": False,
            "settings_write_allowed": False,
            "runtime_score_weight_mutation_allowed": False,
        },
        "safety_boundaries": review["safety_boundaries"],
        "next_step": {
            "name": "Step261",
            "goal": "Connect the review-only selected profile to a manual approval packet, still without auto-applying runtime score weights.",
        },
    }
    return report


def _parse_criteria(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key in [
        "min_rows",
        "min_entry_allowed_ratio",
        "max_entry_allowed_ratio",
        "max_blocked_ratio",
        "max_reduced_ratio",
        "target_entry_allowed_ratio",
        "target_blocked_ratio",
    ]:
        value = getattr(args, key, None)
        if value is not None:
            overrides[key] = value
    return overrides


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step260 review-only ResearchSignal profile calibration report.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--matrix", default=None, help="Optional Feature Store CSV matrix path")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional replay row cap")
    parser.add_argument("--min-rows", type=int, default=None)
    parser.add_argument("--min-entry-allowed-ratio", type=float, default=None)
    parser.add_argument("--max-entry-allowed-ratio", type=float, default=None)
    parser.add_argument("--max-blocked-ratio", type=float, default=None)
    parser.add_argument("--max-reduced-ratio", type=float, default=None)
    parser.add_argument("--target-entry-allowed-ratio", type=float, default=None)
    parser.add_argument("--target-blocked-ratio", type=float, default=None)
    parser.add_argument("--output", default="data/reports/step260_researchsignal_profile_review_only_calibration_report.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    report = build_report(
        root,
        matrix_path=args.matrix,
        max_rows=args.max_rows,
        criteria_overrides=_parse_criteria(args),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    review = report["review"]
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "matrix_source": review["matrix_source"],
        "matrix_source_type": review["matrix_source_type"],
        "rows_evaluated": review["rows_evaluated"],
        "production_candidate_profile": review["candidate_review"]["production_candidate_profile"],
        "auto_apply_selected_profile": review["candidate_review"]["auto_apply_selected_profile"],
        "external_order_submission_performed": review["safety_boundaries"]["external_order_submission_performed"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
