from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import RegistryIntegrityError, registry_path
from crypto_ai_system.registry.prompt_profile_library import (
    ALLOWED_PROMPT_PROFILE_TYPES,
    PROMPT_PROFILE_LIBRARY_REGISTRY_NAME,
    STATUS_PROMPT_PROFILE_LIBRARY_NOOP_ALREADY_SEEDED,
    STATUS_PROMPT_PROFILE_LIBRARY_SEEDED,
    build_prompt_profile_entry,
    build_prompt_profile_registry_record,
    default_prompt_profile_entries,
    run_prompt_profile_library_latest,
    seed_prompt_profile_library,
)


def _cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        settings={
            "storage": {
                "latest_dir": "storage/latest",
                "registry_dir": "storage/registries",
            }
        },
    )


def test_step299_default_prompt_profile_entries_cover_required_types() -> None:
    entries = default_prompt_profile_entries()

    assert len(entries) == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert {entry["type"] for entry in entries} == ALLOWED_PROMPT_PROFILE_TYPES
    for entry in entries:
        assert entry["version"] == "1.0.0"
        assert entry["hash"]
        assert entry["prompt_or_profile_id"].startswith("prompt_profile_")
        assert entry["manual_approval_required_for_runtime_use"] is True
        assert entry["runtime_settings_mutated"] is False
        assert entry["score_weights_mutated"] is False
        assert entry["auto_promotion_allowed"] is False
        assert entry["live_trading_allowed_by_this_module"] is False


def test_step299_seed_prompt_profile_library_persists_append_only_registry(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    summary = seed_prompt_profile_library(cfg=cfg)
    registry = registry_path(cfg, PROMPT_PROFILE_LIBRARY_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert summary["status"] == STATUS_PROMPT_PROFILE_LIBRARY_SEEDED
    assert summary["seeded_count"] == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert summary["registry_record_count"] == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert len(rows) == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert (tmp_path / "storage" / "latest" / "prompt_profile_library.json").exists()
    assert (tmp_path / "storage" / "latest" / "prompt_profile_library_records.json").exists()
    assert all(row["registry_name"] == PROMPT_PROFILE_LIBRARY_REGISTRY_NAME for row in rows)
    assert all(row["prompt_profile_library_record_sha256"] for row in rows)


def test_step299_seed_is_idempotent_for_existing_hashes(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    first = seed_prompt_profile_library(cfg=cfg)
    second = seed_prompt_profile_library(cfg=cfg)
    registry = registry_path(cfg, PROMPT_PROFILE_LIBRARY_REGISTRY_NAME)
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert first["seeded_count"] == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert second["status"] == STATUS_PROMPT_PROFILE_LIBRARY_NOOP_ALREADY_SEEDED
    assert second["seeded_count"] == 0
    assert second["skipped_existing_count"] == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert len(rows) == len(ALLOWED_PROMPT_PROFILE_TYPES)


def test_step299_invalid_prompt_profile_type_fails_closed() -> None:
    with pytest.raises(ValueError):
        build_prompt_profile_entry(
            type="Unsafe Live Trading Prompt",
            purpose="bad",
            body="bad",
            input_needed=["runtime_settings"],
            output_format={"bad": True},
            version="1.0.0",
        )


def test_step299_registry_record_blocks_unsafe_side_effect_flags() -> None:
    entry = build_prompt_profile_entry(
        type="Risk QA Prompt",
        purpose="Validate risk gate.",
        body="Check risk gate evidence only.",
        input_needed=["risk_gate_report"],
        output_format={"risk_gate_status": "PASS|BLOCK"},
        version="1.0.0",
    )
    entry["runtime_settings_mutated"] = True

    record = build_prompt_profile_registry_record(entry)

    assert record["status"] == "PROMPT_PROFILE_LIBRARY_BLOCKED_INVALID_ENTRY"
    assert "UNSAFE_SIDE_EFFECT_FLAG:runtime_settings_mutated" in record["validation_failures"]
    assert record["runtime_settings_mutated"] is False
    assert record["auto_promotion_allowed"] is False


def test_step299_damaged_registry_fails_closed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    registry = registry_path(cfg, PROMPT_PROFILE_LIBRARY_REGISTRY_NAME)
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(RegistryIntegrityError):
        seed_prompt_profile_library(cfg=cfg)


def test_step299_hash_changes_when_prompt_body_changes() -> None:
    base = build_prompt_profile_entry(
        type="Market Thesis Prompt",
        purpose="Build thesis.",
        body="Body A",
        input_needed=["feature_matrix"],
        output_format={"core_thesis": "string"},
        version="1.0.0",
    )
    changed = build_prompt_profile_entry(
        type="Market Thesis Prompt",
        purpose="Build thesis.",
        body="Body B",
        input_needed=["feature_matrix"],
        output_format={"core_thesis": "string"},
        version="1.0.0",
    )

    assert base["hash"] != changed["hash"]
    assert base["prompt_or_profile_id"] != changed["prompt_or_profile_id"]


def test_step299_run_latest_writes_review_only_summary(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    summary = run_prompt_profile_library_latest(cfg=cfg)

    assert summary["registry_record_count"] == len(ALLOWED_PROMPT_PROFILE_TYPES)
    assert summary["review_only"] is True
    assert summary["manual_approval_required_for_runtime_use"] is True
    assert summary["runtime_settings_mutated"] is False
    assert summary["score_weights_mutated"] is False
    assert summary["auto_promotion_allowed"] is False
    assert summary["approval_packet_created"] is False
    assert summary["settings_write_preview_created"] is False
