from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from crypto_ai_system.config import load_config
from crypto_ai_system.features.research_feature_matrix import (
    build_feature_store_manifest,
    persist_feature_store_outputs,
)
from crypto_ai_system.feedback.paper_feedback_integration_report import (
    execute_paper_feedback_integration_report,
    validate_paper_feedback_integration_report,
)
from crypto_ai_system.research.research_signal_profile_approval import (
    build_step261_manual_approval_packet,
    validate_step261_approval_packet,
)
from scripts.report_step260_researchsignal_profile_review_only_calibration import build_report as build_step260_report
from scripts.report_step259_researchsignal_weight_calibration import _synthetic_calibration_matrix


def test_step269_regression_hardening_is_documented() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Step269" in readme and "Regression Hardening" in readme


def test_step269_step214_missing_source_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Step269 feedback integration fails closed"):
        execute_paper_feedback_integration_report(tmp_path, write_output=True)

    with pytest.raises(FileNotFoundError, match="Step269 validation fails closed"):
        validate_paper_feedback_integration_report(tmp_path)


def test_step269_step261_approval_requires_real_source_report(tmp_path: Path) -> None:
    cfg = load_config(".")
    report = build_step260_report(Path(".").resolve(), max_rows=24)
    packet = build_step261_manual_approval_packet(report, cfg)
    validation = validate_step261_approval_packet(packet)

    assert validation["valid"] is False
    assert "source_report_declared" in validation["failed_checks"]
    assert "source_report_present" in validation["failed_checks"]
    assert packet["source"]["source_step_report_exists"] is False

    source_path = tmp_path / "step260_report.json"
    source_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    packet_with_source = build_step261_manual_approval_packet(report, cfg, source_step_report_path=source_path)
    validation_with_source = validate_step261_approval_packet(packet_with_source)

    assert validation_with_source["valid"] is True
    assert packet_with_source["source"]["source_step_report_exists"] is True
    assert packet_with_source["source"]["source_step_report_sha256"]
    assert packet_with_source["source"]["source_step_report_hash_matches"] is True


def test_step269_feature_manifest_uses_upstream_feature_sources_not_matrix_self_reference(tmp_path: Path) -> None:
    source_path = tmp_path / "feature_group_price.csv"
    source_df = pd.DataFrame({"timestamp": ["2026-06-30T00:00:00Z"], "close": [100.0]})
    source_df.to_csv(source_path, index=False)
    matrix_path = tmp_path / "research_feature_matrix_live.csv"
    matrix_df = pd.DataFrame({"timestamp": ["2026-06-30T00:00:00Z"], "close": [100.0]})

    manifest = build_feature_store_manifest(matrix_df, matrix_path=matrix_path, source_files=[source_path])

    assert manifest["matrix_path"] == str(matrix_path)
    assert manifest["source_files"]
    assert manifest["source_files"][0]["path"] == str(source_path)
    assert manifest["source_files"][0]["path"] != manifest["matrix_path"]
    assert manifest["source_files"][0]["sha256"]


def test_step269_persist_feature_outputs_manifest_references_feature_group_sources(tmp_path: Path) -> None:
    cfg = load_config(".")
    cfg.settings.setdefault("storage", {})["features_dir"] = str(tmp_path / "storage" / "features")
    price_features = pd.DataFrame({"timestamp": ["2026-06-30T00:00:00Z"], "close": [100.0]})
    matrix = pd.DataFrame({"timestamp": ["2026-06-30T00:00:00Z"], "close": [100.0]})

    written = persist_feature_store_outputs(
        cfg,
        feature_frames={"price": price_features},
        research_feature_matrix_live=matrix,
    )
    manifest_path = Path(written["research_feature_matrix_live_manifest_json"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert Path(written["price_csv"]).exists()
    assert manifest["source_files"]
    assert all(src["path"] != manifest["matrix_path"] for src in manifest["source_files"])
