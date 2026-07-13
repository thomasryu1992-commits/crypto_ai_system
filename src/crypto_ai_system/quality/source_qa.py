from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.registry.data_snapshot_registry import build_data_snapshot_registry_record, determine_data_quality_status
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

SOURCE_QA_VERSION = "step284_source_qa_v1"

PASS_REVIEW_ONLY = "PASS_REVIEW_ONLY"
PASS_PAPER_ONLY = "PASS_PAPER_ONLY"
BLOCK_MISSING_PRICE = "BLOCK_MISSING_PRICE"
BLOCK_STALE_PRICE = "BLOCK_STALE_PRICE"
BLOCK_FALLBACK_OR_SYNTHETIC = "BLOCK_FALLBACK_OR_SYNTHETIC"
BLOCK_SAMPLE_DATA = "BLOCK_SAMPLE_DATA"
BLOCK_MOCK_DATA = "BLOCK_MOCK_DATA"
BLOCK_SOURCE_BUNDLE_HASH_MISSING = "BLOCK_SOURCE_BUNDLE_HASH_MISSING"
BLOCK_SOURCE_METADATA_INCOMPLETE = "BLOCK_SOURCE_METADATA_INCOMPLETE"


def validate_source_quality(manifest: Mapping[str, Any]) -> dict[str, Any]:
    registry_record = build_data_snapshot_registry_record(manifest)
    block_reasons: list[str] = []
    status = registry_record.get("data_quality_status")

    if not manifest.get("source_bundle_sha256"):
        block_reasons.append(BLOCK_SOURCE_BUNDLE_HASH_MISSING)
    if not manifest.get("data_snapshot_id") or not manifest.get("data_snapshot_sha256"):
        block_reasons.append(BLOCK_SOURCE_METADATA_INCOMPLETE)
    if status == "blocked_missing_price":
        block_reasons.append(BLOCK_MISSING_PRICE)
    if status == "blocked_stale_price":
        block_reasons.append(BLOCK_STALE_PRICE)
    if status in {"blocked_fallback", "blocked_synthetic"}:
        block_reasons.append(BLOCK_FALLBACK_OR_SYNTHETIC)
    if status == "blocked_sample":
        block_reasons.append(BLOCK_SAMPLE_DATA)
    if status == "blocked_mock":
        block_reasons.append(BLOCK_MOCK_DATA)

    optional_missing = list(registry_record.get("optional_sources_missing") or [])
    if block_reasons:
        validation_status = "BLOCK"
    elif optional_missing or not bool(registry_record.get("live_candidate_eligible")):
        validation_status = PASS_REVIEW_ONLY
    else:
        validation_status = PASS_PAPER_ONLY

    payload = {
        "data_snapshot_id": manifest.get("data_snapshot_id"),
        "source_bundle_sha256": manifest.get("source_bundle_sha256"),
        "data_quality_status": status,
        "hard_required_sources_present": bool(registry_record.get("hard_required_sources_present")),
        "optional_sources_missing": optional_missing,
        "missing_optional_source_count": registry_record.get("missing_optional_source_count"),
        "stale_optional_source_count": registry_record.get("stale_optional_source_count"),
        "fallback_flag": registry_record.get("fallback_flag"),
        "synthetic_flag": registry_record.get("synthetic_flag"),
        "sample_flag": registry_record.get("sample_flag"),
        "mock_flag": registry_record.get("mock_flag"),
        "price_source_stale": registry_record.get("price_source_stale"),
        "live_candidate_eligible": bool(registry_record.get("live_candidate_eligible")),
        "live_candidate_block_reasons": registry_record.get("live_candidate_block_reasons") or [],
        "validation_status": validation_status,
        "block_reasons": sorted(set(block_reasons)),
        "created_at_utc": utc_now_canonical(),
        "version": SOURCE_QA_VERSION,
    }
    payload["source_qa_report_id"] = stable_id("source_qa_report", payload, 24)
    payload["source_qa_report_sha256"] = sha256_json(payload)
    return payload


def assert_source_quality_passes(manifest: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_source_quality(manifest)
    if report["validation_status"] == "BLOCK":
        reasons = ",".join(report.get("block_reasons") or [])
        raise ValueError(f"Source QA failed closed: {reasons}")
    return report
