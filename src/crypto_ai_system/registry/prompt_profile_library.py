from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, load_registry_records, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PROMPT_PROFILE_LIBRARY_VERSION = "step299_prompt_profile_library_v1"
PROMPT_PROFILE_LIBRARY_REGISTRY_NAME = "prompt_profile_library"

STATUS_PROMPT_PROFILE_LIBRARY_SEEDED = "PROMPT_PROFILE_LIBRARY_SEEDED"
STATUS_PROMPT_PROFILE_LIBRARY_BLOCKED_INVALID_ENTRY = "PROMPT_PROFILE_LIBRARY_BLOCKED_INVALID_ENTRY"
STATUS_PROMPT_PROFILE_LIBRARY_NOOP_ALREADY_SEEDED = "PROMPT_PROFILE_LIBRARY_NOOP_ALREADY_SEEDED"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE = False

ALLOWED_PROMPT_PROFILE_TYPES = {
    "Data QA Prompt",
    "Feature Lineage Prompt",
    "ResearchSignal Prompt",
    "Market Thesis Prompt",
    "Signal QA Prompt",
    "Risk QA Prompt",
    "Approval QA Prompt",
    "Outcome Analytics Prompt",
    "Candidate Profile Prompt",
    "Review Packet Prompt",
}


@dataclass(frozen=True)
class PromptProfileEntry:
    prompt_or_profile_id: str
    type: str
    purpose: str
    body: str
    input_needed: list[str]
    output_format: dict[str, Any]
    version: str
    quality_score: float
    last_used: str | None
    notes: str
    hash: str
    review_only: bool = True
    manual_approval_required_for_runtime_use: bool = True
    runtime_settings_mutated: bool = RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE
    score_weights_mutated: bool = SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE
    auto_promotion_allowed: bool = AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE
    live_trading_allowed_by_this_module: bool = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    candidate_profile_applied: bool = CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE
    approval_packet_created: bool = APPROVAL_PACKET_CREATED_BY_THIS_MODULE
    settings_write_preview_created: bool = SETTINGS_WRITE_PREVIEW_CREATED_BY_THIS_MODULE
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _normalize_inputs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _normalize_output_format(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if _text(value):
        return {"format": _text(value)}
    return {}


def validate_prompt_profile_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if _text(payload.get("type")) not in ALLOWED_PROMPT_PROFILE_TYPES:
        failures.append("INVALID_PROMPT_PROFILE_TYPE")
    for field_name in ["purpose", "body", "version"]:
        if not _text(payload.get(field_name)):
            failures.append(f"MISSING_{field_name.upper()}")
    if not _normalize_inputs(payload.get("input_needed")):
        failures.append("MISSING_INPUT_NEEDED")
    if not _normalize_output_format(payload.get("output_format")):
        failures.append("MISSING_OUTPUT_FORMAT")
    for flag_name in [
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
        "live_trading_allowed_by_this_module",
        "candidate_profile_applied",
        "approval_packet_created",
        "settings_write_preview_created",
    ]:
        if payload.get(flag_name) is True:
            failures.append(f"UNSAFE_SIDE_EFFECT_FLAG:{flag_name}")
    return not failures, failures


def build_prompt_profile_entry(
    *,
    type: str,
    purpose: str,
    body: str,
    input_needed: Iterable[str],
    output_format: Mapping[str, Any],
    version: str,
    quality_score: float = 1.0,
    last_used: str | None = None,
    notes: str = "",
    prompt_or_profile_id: str | None = None,
) -> dict[str, Any]:
    seed = {
        "type": _text(type),
        "purpose": _text(purpose),
        "body": _text(body),
        "input_needed": _normalize_inputs(input_needed),
        "output_format": _normalize_output_format(output_format),
        "version": _text(version),
        "quality_score": float(quality_score),
        "last_used": last_used,
        "notes": _text(notes),
        "prompt_profile_library_version": PROMPT_PROFILE_LIBRARY_VERSION,
        "review_only": True,
        "manual_approval_required_for_runtime_use": True,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "settings_write_preview_created": False,
    }
    valid, failures = validate_prompt_profile_payload(seed)
    if not valid:
        raise ValueError(f"Invalid prompt/profile entry: {failures}")
    entry_hash = sha256_json(seed)
    entry = PromptProfileEntry(
        prompt_or_profile_id=prompt_or_profile_id or stable_id("prompt_profile", {**seed, "hash": entry_hash}, 24),
        type=seed["type"],
        purpose=seed["purpose"],
        body=seed["body"],
        input_needed=seed["input_needed"],
        output_format=seed["output_format"],
        version=seed["version"],
        quality_score=seed["quality_score"],
        last_used=last_used,
        notes=seed["notes"],
        hash=entry_hash,
    )
    return entry.to_dict()


def default_prompt_profile_entries() -> list[dict[str, Any]]:
    specs = [
        (
            "Data QA Prompt",
            "Validate raw source completeness, freshness, fallback flags, and optional-source neutral policy before feature generation.",
            "Review source metadata. Fail closed for missing/stale/fallback/synthetic/sample price data. Mark optional missing data as neutral_due_to_missing and never live-eligible.",
            ["source_registry_record", "data_snapshot_manifest"],
            {"status": "PASS_REVIEW_ONLY|PASS_PAPER_ONLY|BLOCK", "block_reasons": []},
        ),
        (
            "Feature Lineage Prompt",
            "Check feature matrix reproducibility and lineage before ResearchSignal generation.",
            "Verify data_snapshot_id, feature_snapshot_id, feature_matrix_sha256, source_bundle_sha256, timestamp range, optional-source flags, and hidden fallback absence.",
            ["feature_matrix", "feature_store_manifest", "data_snapshot_manifest"],
            {"feature_lineage_status": "PASS|BLOCK", "missing_fields": []},
        ),
        (
            "ResearchSignal Prompt",
            "Generate ResearchSignal v2 without legacy fallback and preserve all lineage IDs.",
            "Score price direction, derivatives positioning, exchange flow, ETF flow, and stablecoin liquidity. Separate direction from permission and record neutral_due_to_missing.",
            ["feature_matrix", "market_thesis_note", "profile"],
            {"research_signal_id": "string", "permission_result": "allow|reduce|block|neutral|review_only"},
        ),
        (
            "Market Thesis Prompt",
            "Convert feature evidence into human-reviewable market thesis before signal generation.",
            "Separate bullish, bearish, and neutral evidence. Include conflicts, counterarguments, invalidation conditions, and open risks. Do not create orders.",
            ["feature_matrix", "feature_lineage"],
            {"core_thesis": "string", "long_arguments": [], "short_arguments": [], "neutral_arguments": []},
        ),
        (
            "Signal QA Prompt",
            "Validate ResearchSignal integrity before decision permission is authoritative.",
            "Check signal exists, version fields, lineage hashes, registry match, stale/fallback/sample flags, neutral_due_to_missing, and legacy fallback markers.",
            ["research_signal", "research_signal_registry_record"],
            {"signal_qa_result": "PASS_REVIEW_ONLY|PASS_PAPER_ONLY|BLOCK_*", "allowed_for_decision": False},
        ),
        (
            "Risk QA Prompt",
            "Validate PreOrderRiskGate evidence before any order intent or execution stage.",
            "Check approved profile, profile hash, canonical ID chain, data freshness, limits, spread/slippage, API error rate, reconciliation mismatch, kill switch, fee/margin/leverage, and venue readiness.",
            ["trading_decision", "risk_context", "stage_config"],
            {"risk_gate_status": "PASS_REVIEW_ONLY|PASS_PAPER|PASS_SIGNED_TESTNET|BLOCK_*"},
        ),
        (
            "Approval QA Prompt",
            "Validate approval packet and intake records without regenerating missing approval artifacts.",
            "Check packet/intake IDs, approver info, ticket/signature, source report hash, packet hash, feature matrix hash, profile candidate hash, and canonical UTC timestamp.",
            ["approval_packet", "approval_intake", "source_report"],
            {"approval_validation_status": "PASS|BLOCK", "blocked_reason": "string"},
        ),
        (
            "Outcome Analytics Prompt",
            "Analyze reconciled paper/testnet/live-canary outcomes beyond PnL.",
            "Compute expectancy, win/loss ratio, average R, drawdown, slippage, latency, rejection rate, stale data rate, signal-to-outcome drift, paper/live gap, API error rate, and manual overrides.",
            ["reconciliation_record", "execution_record", "decision_record"],
            {"outcome_id": "string", "result_R": 0.0, "next_action": "string"},
        ),
        (
            "Candidate Profile Prompt",
            "Create review-only candidate profile drafts from performance reports without runtime application.",
            "Use performance reports to propose candidate profiles only when sample size, expectancy, failure modes, and safety flags permit. Do not mutate settings or weights.",
            ["performance_report"],
            {"candidate_profile_id": "string", "status": "draft|review_only|rejected"},
        ),
        (
            "Review Packet Prompt",
            "Create review-only packet summaries for human approval without unlocking execution.",
            "Assemble human summary, lineage, signal debug, decision preview, risk gate report, approval candidate, and disabled settings-write preview. Never apply runtime changes.",
            ["registry_records", "candidate_profile", "risk_gate_report"],
            {"review_packet_id": "string", "settings_write_performed": False},
        ),
    ]
    return [
        build_prompt_profile_entry(
            type=type_name,
            purpose=purpose,
            body=body,
            input_needed=inputs,
            output_format=output_format,
            version="1.0.0",
            quality_score=1.0,
            last_used=None,
            notes="Seeded by Step299 Prompt/Profile Library. Runtime use requires manual approval.",
        )
        for type_name, purpose, body, inputs, output_format in specs
    ]


def build_prompt_profile_registry_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(entry or {})
    valid, failures = validate_prompt_profile_payload(payload)
    if not valid:
        return {
            "prompt_profile_library_version": PROMPT_PROFILE_LIBRARY_VERSION,
            "prompt_or_profile_id": payload.get("prompt_or_profile_id"),
            "type": payload.get("type"),
            "status": STATUS_PROMPT_PROFILE_LIBRARY_BLOCKED_INVALID_ENTRY,
            "validation_failures": failures,
            "review_only": True,
            "manual_approval_required_for_runtime_use": True,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "live_trading_allowed_by_this_module": False,
            "candidate_profile_applied": False,
            "approval_packet_created": False,
            "settings_write_preview_created": False,
            "created_at_utc": utc_now_canonical(),
        }
    record = {
        "prompt_profile_library_version": PROMPT_PROFILE_LIBRARY_VERSION,
        "prompt_or_profile_id": payload.get("prompt_or_profile_id"),
        "type": payload.get("type"),
        "purpose": payload.get("purpose"),
        "body": payload.get("body"),
        "input_needed": payload.get("input_needed") or [],
        "output_format": payload.get("output_format") or {},
        "version": payload.get("version"),
        "quality_score": payload.get("quality_score", 0.0),
        "last_used": payload.get("last_used"),
        "notes": payload.get("notes"),
        "hash": payload.get("hash") or sha256_json(payload),
        "status": STATUS_PROMPT_PROFILE_LIBRARY_SEEDED,
        "review_only": payload.get("review_only", True),
        "manual_approval_required_for_runtime_use": payload.get("manual_approval_required_for_runtime_use", True),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "settings_write_preview_created": False,
        "created_at_utc": payload.get("created_at_utc") or utc_now_canonical(),
    }
    record["prompt_profile_library_record_id"] = stable_id("prompt_profile_library", record, 24)
    record["prompt_profile_library_record_sha256"] = sha256_json(record)
    return record


def seed_prompt_profile_library(
    entries: Iterable[Mapping[str, Any]] | None = None,
    *,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    entries_to_seed = [dict(item) for item in (entries or default_prompt_profile_entries())]
    path = registry_path(cfg, PROMPT_PROFILE_LIBRARY_REGISTRY_NAME)
    existing = load_registry_records(path)
    existing_hashes = {str(row.get("hash")) for row in existing if row.get("hash")}
    persisted_records: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    invalid_records: list[dict[str, Any]] = []

    for entry in entries_to_seed:
        record = build_prompt_profile_registry_record(entry)
        if record.get("status") == STATUS_PROMPT_PROFILE_LIBRARY_BLOCKED_INVALID_ENTRY:
            invalid_records.append(record)
            continue
        entry_hash = str(record.get("hash"))
        if entry_hash in existing_hashes:
            skipped_existing.append(entry_hash)
            continue
        persisted = append_registry_record(
            path,
            record,
            registry_name=PROMPT_PROFILE_LIBRARY_REGISTRY_NAME,
            id_field="prompt_profile_library_record_id",
            hash_field="prompt_profile_library_record_sha256",
            id_prefix="prompt_profile_library",
        )
        persisted_records.append(persisted)
        existing_hashes.add(entry_hash)

    latest_records = load_registry_records(path)
    type_counts: dict[str, int] = {}
    for row in latest_records:
        row_type = _text(row.get("type")) or "unknown"
        type_counts[row_type] = type_counts.get(row_type, 0) + 1

    summary = {
        "prompt_profile_library_version": PROMPT_PROFILE_LIBRARY_VERSION,
        "status": STATUS_PROMPT_PROFILE_LIBRARY_SEEDED if persisted_records else STATUS_PROMPT_PROFILE_LIBRARY_NOOP_ALREADY_SEEDED,
        "default_type_count": len(ALLOWED_PROMPT_PROFILE_TYPES),
        "input_entry_count": len(entries_to_seed),
        "seeded_count": len(persisted_records),
        "skipped_existing_count": len(skipped_existing),
        "invalid_entry_count": len(invalid_records),
        "registry_record_count": len(latest_records),
        "prompt_profile_types": sorted(ALLOWED_PROMPT_PROFILE_TYPES),
        "prompt_profile_type_counts": dict(sorted(type_counts.items())),
        "seeded_record_ids": [row.get("prompt_profile_library_record_id") for row in persisted_records],
        "seeded_hashes": [row.get("hash") for row in persisted_records],
        "invalid_records": invalid_records,
        "review_only": True,
        "manual_approval_required_for_runtime_use": True,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "candidate_profile_applied": False,
        "approval_packet_created": False,
        "settings_write_preview_created": False,
        "created_at_utc": utc_now_canonical(),
    }
    summary["prompt_profile_library_summary_id"] = stable_id("prompt_profile_library_summary", summary, 24)
    summary["prompt_profile_library_summary_sha256"] = sha256_json(summary)
    atomic_write_json(_latest_path(cfg, "prompt_profile_library.json"), summary)
    atomic_write_json(_latest_path(cfg, "prompt_profile_library_records.json"), latest_records)
    return summary


def run_prompt_profile_library_latest(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    return seed_prompt_profile_library(cfg=cfg or load_config("."))
