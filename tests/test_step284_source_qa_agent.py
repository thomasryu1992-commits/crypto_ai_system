from __future__ import annotations

from crypto_ai_system.quality.source_qa import (
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_MISSING_PRICE,
    PASS_PAPER_ONLY,
    PASS_REVIEW_ONLY,
    validate_source_quality,
)


def _manifest(**overrides):
    base = {
        "data_snapshot_id": "data_snapshot_step284",
        "data_snapshot_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "raw_frames": {
            "ohlcv_raw": {
                "rows": 10,
                "columns": ["timestamp", "close"],
                "frame_sha256": "c" * 64,
                "min_timestamp_utc": "2026-06-01T00:00:00Z",
                "max_timestamp_utc": "2026-06-01T09:00:00Z",
            }
        },
        "source_files": {},
        "source_status": {},
        "optional_data_health": {},
        "missing_optional_source_count": 0,
        "stale_optional_source_count": 0,
        "live_candidate_eligible": True,
        "created_at_utc": "2026-06-30T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_step284_source_qa_passes_paper_only_for_valid_price_and_sources() -> None:
    report = validate_source_quality(_manifest())

    assert report["validation_status"] == PASS_PAPER_ONLY
    assert report["block_reasons"] == []
    assert report["hard_required_sources_present"] is True


def test_step284_source_qa_passes_review_only_when_optional_source_missing() -> None:
    report = validate_source_quality(
        _manifest(
            optional_data_health={"farside_etf_flow": {"neutral_due_to_missing": True, "stale": False}},
            live_candidate_eligible=False,
        )
    )

    assert report["validation_status"] == PASS_REVIEW_ONLY
    assert report["optional_sources_missing"] == ["farside_etf_flow"]
    assert report["block_reasons"] == []


def test_step284_source_qa_blocks_missing_price() -> None:
    report = validate_source_quality(_manifest(raw_frames={}))

    assert report["validation_status"] == "BLOCK"
    assert BLOCK_MISSING_PRICE in report["block_reasons"]


def test_step284_source_qa_blocks_fallback_or_synthetic_source_status() -> None:
    report = validate_source_quality(_manifest(source_status={"price": {"source": "fallback_price_data"}}))

    assert report["validation_status"] == "BLOCK"
    assert BLOCK_FALLBACK_OR_SYNTHETIC in report["block_reasons"]
