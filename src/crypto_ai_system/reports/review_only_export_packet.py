from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.agents.agent_library_export import (
    AGENT_LIBRARY_EXPORT_FILE_NAMES,
    collect_agent_library_export_artifacts,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

REVIEW_ONLY_EXPORT_PACKET_VERSION = "step326_review_only_export_packet_with_agent_library_v1"
REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME = "review_only_export_packet_registry"

STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED = "REVIEW_ONLY_EXPORT_PACKET_CREATED"
STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED_WITH_MISSING_ARTIFACTS = "REVIEW_ONLY_EXPORT_PACKET_CREATED_WITH_MISSING_ARTIFACTS"

LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
SETTINGS_WRITE_PREVIEW_APPLIED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False

EXPORT_FILE_MAP: dict[str, tuple[str, ...]] = {
    "feature_lineage.json": ("research_signal.json",),
    "research_signal_debug.json": ("research_signal.json",),
    "market_thesis_note.json": ("market_thesis_note.json",),
    "paper_decision_preview.json": ("trade_decision.json", "latest_trade_decision.json"),
    "risk_gate_report.json": ("trade_decision.json", "latest_trade_decision.json"),
    "approval_packet_candidate.json": ("candidate_profile.json",),
}

REQUIRED_EXPORT_FILES: tuple[str, ...] = (
    "human_review_summary.md",
    "feature_lineage.json",
    "research_signal_debug.json",
    "market_thesis_note.json",
    "paper_decision_preview.json",
    "risk_gate_report.json",
    "approval_packet_candidate.json",
    "candidate_settings.yaml",
    "disabled_settings_write_preview.diff",
    *AGENT_LIBRARY_EXPORT_FILE_NAMES,
    "review_only_export_packet_manifest.json",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _export_root(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.review_export_dir", "storage/review_packets")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_latest_json(latest: Path, name: str) -> dict[str, Any]:
    value = read_json(latest / name, default={})
    return _as_mapping(value)


def _read_first_latest_json(latest: Path, *names: str) -> dict[str, Any]:
    for name in names:
        payload = _read_latest_json(latest, name)
        if payload:
            return payload
    return {}


def _safe_subset(payload: Mapping[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys if key in payload}


def _feature_lineage_from_signal(signal: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _as_mapping(signal.get("feature_snapshot_manifest"))
    return {
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        "data_snapshot_id": signal.get("data_snapshot_id") or manifest.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": signal.get("data_snapshot_manifest_sha256") or manifest.get("data_snapshot_manifest_sha256"),
        "feature_snapshot_id": signal.get("feature_snapshot_id") or manifest.get("feature_snapshot_id"),
        "feature_matrix_sha256": signal.get("feature_matrix_sha256") or manifest.get("feature_matrix_sha256"),
        "source_bundle_sha256": signal.get("source_bundle_sha256") or manifest.get("source_bundle_sha256"),
        "optional_data_health": signal.get("optional_data_health") or manifest.get("optional_data_health") or {},
        "missing_optional_source_count": signal.get("missing_optional_source_count") or manifest.get("missing_optional_source_count"),
        "stale_optional_source_count": signal.get("stale_optional_source_count") or manifest.get("stale_optional_source_count"),
        "live_candidate_eligible": signal.get("live_candidate_eligible") is True,
        "feature_snapshot_manifest": manifest,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }


def _risk_gate_report_from_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    report = _as_mapping(decision.get("pre_order_risk_gate") or decision.get("risk_gate_report"))
    if report:
        return report
    return {
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        "risk_gate_id": decision.get("risk_gate_id"),
        "risk_gate_status": decision.get("risk_gate_status"),
        "pre_order_risk_gate_required": decision.get("pre_order_risk_gate_required", True),
        "pre_order_risk_gate_approved": decision.get("pre_order_risk_gate_approved", False),
        "order_intent_block_reason": decision.get("order_intent_block_reason"),
        "allow_order_intent": decision.get("allow_order_intent", False),
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }


def _paper_decision_preview(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        **_safe_subset(
            decision,
            [
                "decision_id",
                "decision_stage",
                "final_decision",
                "direction",
                "entry",
                "stop_loss",
                "take_profit",
                "risk_reward",
                "invalidation",
                "allow_long",
                "allow_short",
                "allow_new_position",
                "allow_order_intent",
                "pre_order_risk_gate_required",
                "pre_order_risk_gate_approved",
                "order_intent_created",
                "order_intent_block_reason",
                "signal_permission_authoritative",
                "research_signal_id",
                "risk_gate_id",
            ],
        ),
        "review_only": True,
        "order_submission_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }


def _research_signal_debug(signal: Mapping[str, Any], registry_record: Mapping[str, Any], signal_qa: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        "research_signal": dict(signal),
        "research_signal_registry_record": dict(registry_record),
        "signal_qa_report": dict(signal_qa),
        "live_candidate_eligible": signal.get("live_candidate_eligible") is True,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }


def _approval_packet_candidate(candidate: Mapping[str, Any], approval_registry: Mapping[str, Any], performance_report: Mapping[str, Any]) -> dict[str, Any]:
    identity = {
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "source_report_id": candidate.get("source_report_id") or performance_report.get("performance_report_id"),
        "profile_candidate_hash": candidate.get("profile_candidate_hash"),
        "feature_matrix_sha256": candidate.get("feature_matrix_sha256") or performance_report.get("feature_matrix_sha256"),
        "created_at_utc": utc_now_canonical(),
        "mode": "review_only_approval_packet_candidate_preview",
    }
    packet = {
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        "approval_packet_candidate_id": stable_id("approval_packet_candidate", identity, 24),
        "mode": "review_only_approval_packet_candidate_preview",
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "candidate_profile_status": candidate.get("status"),
        "candidate_profile_creation_status": candidate.get("creation_status"),
        "source_report_id": identity["source_report_id"],
        "source_report_hash": candidate.get("source_report_hash") or performance_report.get("performance_report_sha256"),
        "feature_matrix_sha256": identity["feature_matrix_sha256"],
        "profile_candidate_hash": identity["profile_candidate_hash"],
        "approval_registry_validation_status": approval_registry.get("validation_status"),
        "approval_registry_blocked_reasons": approval_registry.get("blocked_reasons") or [],
        "manual_approval_required": True,
        "approval_packet_created_by_this_module": False,
        "approval_intake_created_by_this_module": False,
        "approval_file_auto_regenerated_by_this_module": False,
        "candidate_profile_applied": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": identity["created_at_utc"],
    }
    packet["approval_packet_candidate_sha256"] = sha256_json({k: v for k, v in packet.items() if k != "approval_packet_candidate_sha256"})
    return packet


def _disabled_settings_write_preview_diff(candidate: Mapping[str, Any], approval_registry: Mapping[str, Any]) -> str:
    candidate_id = _text(candidate.get("candidate_profile_id")) or "<no-candidate-profile>"
    approval_status = _text(approval_registry.get("validation_status")) or "blocked_fail_closed"
    return "\n".join(
        [
            "# disabled_settings_write_preview.diff",
            "# REVIEW ONLY. This file documents that no runtime settings write is allowed in Step302.",
            "--- config/settings.yaml",
            "+++ config/settings.yaml.disabled-preview",
            f"# candidate_profile_id: {candidate_id}",
            f"# approval_validation_status: {approval_status}",
            "# No YAML mutation is generated by this module.",
            "# Runtime settings mutation: disabled",
            "# Runtime score_weights mutation: disabled",
            "# Signed testnet promotion: disabled",
            "# Live promotion: disabled",
            "# Automatic apply: disabled",
            "",
        ]
    )


def _human_review_summary(context: Mapping[str, Any]) -> str:
    decision = _as_mapping(context.get("decision"))
    signal = _as_mapping(context.get("research_signal"))
    approval = _as_mapping(context.get("approval_registry"))
    candidate = _as_mapping(context.get("candidate_profile"))
    performance = _as_mapping(context.get("performance_report"))
    agent_library = _as_mapping(context.get("agent_library_contract_review"))
    missing = list(context.get("missing_source_artifacts") or [])
    lines = [
        "# Step302 Review-only Export Packet v2",
        "",
        "## Current Status",
        f"- Final decision: {_text(decision.get('final_decision')) or 'unknown'}",
        f"- ResearchSignal ID: {_text(signal.get('research_signal_id') or signal.get('signal_id')) or 'missing'}",
        f"- Signal permission: {_text(signal.get('permission_result')) or 'unknown'}",
        f"- Live candidate eligible: {signal.get('live_candidate_eligible') is True}",
        f"- Performance report status: {_text(performance.get('status')) or 'missing'}",
        f"- Candidate profile status: {_text(candidate.get('status')) or 'missing'}",
        f"- Approval validation status: {_text(approval.get('validation_status')) or 'missing'}",
        f"- Agent Library review status: {_text(agent_library.get('status')) or 'missing'}",
        "",
        "## Safety Invariants",
        "- Runtime settings mutation: disabled",
        "- Runtime score_weights mutation: disabled",
        "- Approval packet creation by this module: disabled",
        "- Candidate profile application: disabled",
        "- Testnet order submission: disabled",
        "- Live order execution: disabled",
        "- Automatic promotion: disabled",
        "",
        "## Exported Files",
        *[f"- {name}" for name in REQUIRED_EXPORT_FILES],
    ]
    if missing:
        lines.extend(["", "## Missing Source Artifacts", *[f"- {name}" for name in missing]])
    lines.extend([
        "",
        "## Operator Note",
        "This packet is for manual review only. It must not be treated as approval, runtime configuration, signed testnet unlock, or live trading authorization.",
        "",
    ])
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash_exported_files(packet_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(packet_dir.iterdir()):
        if path.is_file() and path.name != "review_only_export_packet_manifest.json":
            hashes[path.name] = sha256_file(path)
    return hashes


def build_review_only_export_packet_context(cfg: AppConfig) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    research_signal = _read_latest_json(latest, "research_signal.json")
    decision = _read_first_latest_json(latest, "trade_decision.json", "latest_trade_decision.json")
    market_thesis_note = _read_latest_json(latest, "market_thesis_note.json")
    research_signal_registry = _read_latest_json(latest, "research_signal_registry_record.json")
    signal_qa = _read_latest_json(latest, "signal_qa_report.json")
    performance_report = _read_latest_json(latest, "performance_report.json")
    candidate_profile = _read_latest_json(latest, "candidate_profile.json")
    approval_registry = _read_latest_json(latest, "approval_registry_record.json")
    settings_write_preview = _read_latest_json(latest, "settings_write_preview_guard_manifest.json")
    agent_library_contract_review = _read_latest_json(latest, "agent_library_contract_review_report.json")
    return {
        "research_signal": research_signal,
        "decision": decision,
        "market_thesis_note": market_thesis_note,
        "research_signal_registry": research_signal_registry,
        "signal_qa": signal_qa,
        "performance_report": performance_report,
        "candidate_profile": candidate_profile,
        "approval_registry": approval_registry,
        "settings_write_preview": settings_write_preview,
        "agent_library_contract_review": agent_library_contract_review,
    }


def build_and_persist_review_only_export_packet(*, cfg: AppConfig | None = None, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    context_payload = dict(context or build_review_only_export_packet_context(cfg))
    latest = _latest_dir(cfg)
    export_root = _export_root(cfg)

    identity = {
        "research_signal_id": _as_mapping(context_payload.get("research_signal")).get("research_signal_id") or _as_mapping(context_payload.get("research_signal")).get("signal_id"),
        "decision_id": _as_mapping(context_payload.get("decision")).get("decision_id"),
        "candidate_profile_id": _as_mapping(context_payload.get("candidate_profile")).get("candidate_profile_id"),
        "approval_registry_record_id": _as_mapping(context_payload.get("approval_registry")).get("approval_registry_record_id"),
        "settings_write_preview_guard_id": _as_mapping(context_payload.get("settings_write_preview")).get("settings_write_preview_guard_id"),
        "created_at_utc": utc_now_canonical(),
        "version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
    }
    packet_id = stable_id("review_packet", identity, 24)
    packet_dir = export_root / packet_id
    packet_dir.mkdir(parents=True, exist_ok=True)

    signal = _as_mapping(context_payload.get("research_signal"))
    decision = _as_mapping(context_payload.get("decision"))
    market_thesis = _as_mapping(context_payload.get("market_thesis_note"))
    signal_registry = _as_mapping(context_payload.get("research_signal_registry"))
    signal_qa = _as_mapping(context_payload.get("signal_qa"))
    performance = _as_mapping(context_payload.get("performance_report"))
    candidate = _as_mapping(context_payload.get("candidate_profile"))
    approval = _as_mapping(context_payload.get("approval_registry"))
    settings_preview = _as_mapping(context_payload.get("settings_write_preview"))
    agent_library_review = _as_mapping(context_payload.get("agent_library_contract_review"))

    candidate_settings_text = "# candidate_settings.yaml missing. Step302 settings preview guard did not produce a candidate settings artifact.\n"
    candidate_settings_path = settings_preview.get("candidate_settings_path")
    if candidate_settings_path and Path(str(candidate_settings_path)).exists():
        candidate_settings_text = Path(str(candidate_settings_path)).read_text(encoding="utf-8")

    disabled_diff_text = _disabled_settings_write_preview_diff(candidate, approval)
    disabled_diff_path = settings_preview.get("disabled_settings_write_preview_diff_path")
    if disabled_diff_path and Path(str(disabled_diff_path)).exists():
        disabled_diff_text = Path(str(disabled_diff_path)).read_text(encoding="utf-8")

    artifacts = {
        "human_review_summary.md": _human_review_summary({**context_payload, "missing_source_artifacts": []}),
        "feature_lineage.json": _feature_lineage_from_signal(signal),
        "research_signal_debug.json": _research_signal_debug(signal, signal_registry, signal_qa),
        "market_thesis_note.json": market_thesis or {"missing": True, "review_only": True},
        "paper_decision_preview.json": _paper_decision_preview(decision),
        "risk_gate_report.json": _risk_gate_report_from_decision(decision),
        "approval_packet_candidate.json": _approval_packet_candidate(candidate, approval, performance),
        "candidate_settings.yaml": candidate_settings_text,
        "disabled_settings_write_preview.diff": disabled_diff_text,
    }
    agent_artifacts, missing_agent_library_artifacts = collect_agent_library_export_artifacts(cfg)
    artifacts.update(agent_artifacts)

    missing_source_artifacts = [name for name, sources in EXPORT_FILE_MAP.items() if sources and not any((latest / source).exists() for source in sources)]
    if missing_source_artifacts:
        artifacts["human_review_summary.md"] = _human_review_summary({**context_payload, "missing_source_artifacts": missing_source_artifacts})

    exported_paths: dict[str, str] = {}
    for filename, payload in artifacts.items():
        path = packet_dir / filename
        if filename.endswith(".json"):
            atomic_write_json(path, payload)
        else:
            _write_text(path, str(payload))
        exported_paths[filename] = str(path)

    file_hashes = _hash_exported_files(packet_dir)
    status = STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED_WITH_MISSING_ARTIFACTS if missing_source_artifacts else STATUS_REVIEW_ONLY_EXPORT_PACKET_CREATED
    manifest = {
        "review_only_export_packet_id": packet_id,
        "review_only_export_packet_version": REVIEW_ONLY_EXPORT_PACKET_VERSION,
        "status": status,
        "packet_dir": str(packet_dir),
        "exported_files": sorted(exported_paths.keys()),
        "exported_file_hashes": file_hashes,
        "missing_source_artifacts": missing_source_artifacts,
        "research_signal_id": signal.get("research_signal_id") or signal.get("signal_id"),
        "data_snapshot_id": signal.get("data_snapshot_id"),
        "feature_snapshot_id": signal.get("feature_snapshot_id"),
        "feature_matrix_sha256": signal.get("feature_matrix_sha256"),
        "source_bundle_sha256": signal.get("source_bundle_sha256"),
        "market_thesis_note_id": market_thesis.get("market_thesis_note_id"),
        "decision_id": decision.get("decision_id"),
        "risk_gate_id": decision.get("risk_gate_id") or _as_mapping(decision.get("pre_order_risk_gate")).get("risk_gate_id"),
        "candidate_profile_id": candidate.get("candidate_profile_id"),
        "approval_registry_record_id": approval.get("approval_registry_record_id"),
        "settings_write_preview_guard_id": settings_preview.get("settings_write_preview_guard_id"),
        "settings_write_preview_status": settings_preview.get("status"),
        "candidate_settings_path": settings_preview.get("candidate_settings_path"),
        "disabled_settings_write_preview_diff_path": settings_preview.get("disabled_settings_write_preview_diff_path"),
        "agent_library_contract_review_status": agent_library_review.get("status"),
        "agent_library_contract_review_report_id": agent_library_review.get("agent_library_contract_review_report_id"),
        "agent_library_contract_review_report_sha256": agent_library_review.get("agent_library_contract_review_report_sha256"),
        "agent_library_exported_files": sorted(AGENT_LIBRARY_EXPORT_FILE_NAMES),
        "missing_agent_library_artifacts": missing_agent_library_artifacts,
        "agent_library_evidence_status": "AGENT_LIBRARY_EVIDENCE_INCLUDED" if not missing_agent_library_artifacts else "AGENT_LIBRARY_EVIDENCE_BLOCKED_MISSING_ARTIFACTS",
        "review_only": True,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "approval_packet_created_by_this_module": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "external_order_submission_performed": False,
        "live_trading_allowed_by_this_module": False,
        "auto_promotion_allowed": False,
        "created_at_utc": identity["created_at_utc"],
    }
    manifest["review_only_export_packet_manifest_sha256"] = sha256_json({k: v for k, v in manifest.items() if k != "review_only_export_packet_manifest_sha256"})
    atomic_write_json(packet_dir / "review_only_export_packet_manifest.json", manifest)
    exported_paths["review_only_export_packet_manifest.json"] = str(packet_dir / "review_only_export_packet_manifest.json")

    registry_record = append_registry_record(
        registry_path(cfg, REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME),
        manifest,
        registry_name=REVIEW_ONLY_EXPORT_PACKET_REGISTRY_NAME,
        id_field="review_only_export_packet_registry_record_id",
        hash_field="review_only_export_packet_registry_record_sha256",
        id_prefix="review_packet_registry",
    )
    manifest["review_only_export_packet_registry_record_id"] = registry_record["review_only_export_packet_registry_record_id"]
    manifest["review_only_export_packet_registry_record_sha256"] = registry_record["review_only_export_packet_registry_record_sha256"]
    atomic_write_json(packet_dir / "review_only_export_packet_manifest.json", manifest)
    atomic_write_json(latest / "review_only_export_packet_manifest.json", manifest)
    atomic_write_json(latest / "review_only_export_packet_registry_record.json", registry_record)
    return manifest


def run_review_only_export_packet_latest(cfg: AppConfig | None = None) -> dict[str, Any]:
    return build_and_persist_review_only_export_packet(cfg=cfg or load_config())
