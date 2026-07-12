from __future__ import annotations

import json
from pathlib import Path

import yaml

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.reports.review_only_export_packet import build_and_persist_review_only_export_packet
from crypto_ai_system.reports.settings_write_preview_guard import (
    SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME,
    SETTINGS_WRITE_PREVIEW_GUARD_VERSION,
    STATUS_BLOCKED_SETTINGS_SOURCE_MISSING,
    STATUS_CREATED_BLOCKED_REVIEW_ONLY,
    STATUS_CREATED_REVIEW_ONLY,
    build_and_persist_settings_write_preview_guard,
    build_settings_write_preview_guard,
    run_settings_write_preview_guard_latest,
)


def _cfg(tmp_path: Path) -> AppConfig:
    settings = {
        "project": {"version": "step286_researchsignal_feature_lineage_fix"},
        "storage": {
            "latest_dir": "storage/latest",
            "registry_dir": "storage/registries",
            "settings_write_preview_dir": "storage/settings_write_previews",
            "review_export_dir": "storage/review_packets",
        },
        "research": {
            "score_weights": {
                "structure": 0.2,
                "momentum": 0.1,
                "derivatives": 0.25,
                "exchange_flow": 0.15,
                "etf_flow": 0.15,
                "stablecoin_liquidity": 0.1,
                "risk": 0.05,
                "onchain": 0.0,
            }
        },
        "safety": {"live_trading_enabled": False, "testnet_signed_order_enabled": False},
        "execution": {"explicit_signed_testnet_execution_approval_packet": {"testnet_order_submission_allowed": False}},
    }
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "settings.yaml").write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return AppConfig(root=tmp_path, settings=settings)


def _ready_candidate() -> dict:
    return {
        "candidate_profile_id": "candidate_step302",
        "candidate_profile_created": True,
        "status": "review_only",
        "creation_status": "CANDIDATE_PROFILE_DRAFT_CREATED_REVIEW_ONLY",
        "profile_candidate_hash": "profile_hash_step302",
        "proposed_score_weights": {
            "structure": 0.3,
            "momentum": 0.1,
            "derivatives": 0.2,
            "exchange_flow": 0.15,
            "etf_flow": 0.1,
            "stablecoin_liquidity": 0.1,
            "risk": 0.05,
            "onchain": 0.0,
        },
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
    }


def _valid_approval() -> dict:
    return {
        "approval_registry_record_id": "approval_registry_step302",
        "approval_registry_record_sha256": "approval_registry_hash_step302",
        "validation_status": "valid",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "approval_file_auto_regenerated_by_this_module": False,
    }


def test_step302_builds_review_only_candidate_settings_and_disabled_diff(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    manifest = build_and_persist_settings_write_preview_guard(
        cfg=cfg,
        candidate_profile=_ready_candidate(),
        approval_registry=_valid_approval(),
    )

    assert manifest["settings_write_preview_guard_version"] == SETTINGS_WRITE_PREVIEW_GUARD_VERSION
    assert manifest["status"] == STATUS_CREATED_REVIEW_ONLY
    assert manifest["candidate_settings_changed"] is True
    assert manifest["settings_file_write_enabled"] is False
    assert manifest["apply_preview_enabled"] is False
    assert manifest["runtime_settings_mutated"] is False
    assert manifest["score_weights_mutated"] is False
    assert manifest["candidate_profile_applied"] is False
    assert manifest["auto_promotion_allowed"] is False
    assert manifest["testnet_order_submission_allowed_by_this_module"] is False
    assert manifest["external_order_submission_performed"] is False
    assert manifest["live_trading_allowed_by_this_module"] is False

    candidate_yaml = Path(manifest["candidate_settings_path"]).read_text(encoding="utf-8")
    diff = Path(manifest["disabled_settings_write_preview_diff_path"]).read_text(encoding="utf-8")
    assert "structure: 0.3" in candidate_yaml
    assert "REVIEW ONLY" in diff
    assert "Runtime settings mutation: disabled" in diff
    assert "Automatic apply: disabled" in diff
    assert (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8") != candidate_yaml


def test_step302_blocks_but_renders_noop_preview_when_candidate_or_approval_not_ready(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    candidate = {"candidate_profile_id": "blocked", "candidate_profile_created": False, "status": "rejected"}
    approval = {"validation_status": "blocked_fail_closed"}

    manifest = build_and_persist_settings_write_preview_guard(cfg=cfg, candidate_profile=candidate, approval_registry=approval)

    assert manifest["status"] == STATUS_CREATED_BLOCKED_REVIEW_ONLY
    assert "CANDIDATE_PROFILE_NOT_READY_FOR_SETTINGS_PREVIEW" in manifest["blocked_reasons"]
    assert "APPROVAL_REGISTRY_NOT_VALID_FOR_SETTINGS_PREVIEW" in manifest["blocked_reasons"]
    assert manifest["settings_file_write_enabled"] is False
    assert manifest["runtime_settings_mutated"] is False
    diff = Path(manifest["disabled_settings_write_preview_diff_path"]).read_text(encoding="utf-8")
    assert "blocked_reasons" in diff
    assert "Settings file write: disabled" in diff


def test_step302_missing_settings_source_fails_closed_without_reconstruction(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    (tmp_path / "config" / "settings.yaml").unlink()

    preview = build_settings_write_preview_guard(cfg=cfg, candidate_profile=_ready_candidate(), approval_registry=_valid_approval())

    assert preview["status"] == STATUS_BLOCKED_SETTINGS_SOURCE_MISSING
    assert "SETTINGS_SOURCE_FILE_MISSING" in preview["blocked_reasons"]
    assert preview["runtime_settings_mutated"] is False
    assert preview["score_weights_mutated"] is False


def test_step302_persists_registry_and_latest_mirrors(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "candidate_profile.json", _ready_candidate())
    atomic_write_json(latest / "approval_registry_record.json", _valid_approval())

    manifest = run_settings_write_preview_guard_latest(cfg=cfg)
    registry = registry_path(cfg, SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["registry_name"] == SETTINGS_WRITE_PREVIEW_GUARD_REGISTRY_NAME
    assert rows[0]["settings_write_preview_guard_id"] == manifest["settings_write_preview_guard_id"]
    assert rows[0]["runtime_settings_mutated"] is False
    assert (latest / "settings_write_preview_guard_manifest.json").exists()
    assert (latest / "settings_write_preview_guard_registry_record.json").exists()


def test_step302_review_export_packet_uses_guarded_candidate_settings_and_diff(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "candidate_profile.json", _ready_candidate())
    atomic_write_json(latest / "approval_registry_record.json", _valid_approval())
    atomic_write_json(latest / "research_signal.json", {"research_signal_id": "signal_step302", "feature_snapshot_id": "feature_step302"})
    atomic_write_json(latest / "trade_decision.json", {"decision_id": "decision_step302", "allow_order_intent": False})
    run_settings_write_preview_guard_latest(cfg=cfg)

    packet = build_and_persist_review_only_export_packet(cfg=cfg)
    packet_dir = Path(packet["packet_dir"])

    assert "candidate_settings.yaml" in packet["exported_files"]
    assert "disabled_settings_write_preview.diff" in packet["exported_files"]
    assert packet["settings_write_preview_status"] == STATUS_CREATED_REVIEW_ONLY
    assert packet["settings_write_preview_applied"] is False
    assert packet["runtime_settings_mutated"] is False
    assert "structure: 0.3" in (packet_dir / "candidate_settings.yaml").read_text(encoding="utf-8")
    assert "Step302 Settings Write Preview Guard v2" in (packet_dir / "disabled_settings_write_preview.diff").read_text(encoding="utf-8")
