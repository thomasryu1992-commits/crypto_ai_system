from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP317_DEPLOYMENT_RUNBOOK_VERSION = "step317_deployment_runbook_v1"
DEPLOYMENT_RUNBOOK_REGISTRY_NAME = "deployment_runbook_registry"

STATUS_RECORDED_REVIEW_ONLY = "DEPLOYMENT_RUNBOOK_REVIEW_ONLY_RECORDED"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "DEPLOYMENT_RUNBOOK_BLOCKED_UNSAFE_SIDE_EFFECT"

BLOCK_UNSAFE_SIDE_EFFECT = "STEP317_BLOCK_UNSAFE_SIDE_EFFECT"
BLOCK_DEPLOYMENT_EXECUTION_ATTEMPT = "STEP317_BLOCK_DEPLOYMENT_EXECUTION_ATTEMPT"
BLOCK_PROCESS_CONTROL_ATTEMPT = "STEP317_BLOCK_PROCESS_CONTROL_ATTEMPT"
BLOCK_SECRET_VALUE_ACCESS = "STEP317_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_RUNTIME_MUTATION = "STEP317_BLOCK_RUNTIME_MUTATION"
BLOCK_LIVE_EXECUTION = "STEP317_BLOCK_LIVE_EXECUTION"
BLOCK_NOTIFICATION_SEND_ATTEMPT = "STEP317_BLOCK_NOTIFICATION_SEND_ATTEMPT"

REQUIRED_SECTION_IDS = [
    "ENVIRONMENT_SETUP",
    "METADATA_ONLY_SECRET_INJECTION",
    "PROCESS_START_STOP",
    "MANUAL_KILL_SWITCH",
    "LOG_PATHS",
    "BACKUP_PATHS",
    "INCIDENT_RESPONSE",
    "ROLLBACK",
    "DAILY_REVIEW",
    "DISABLED_RUNTIME_GUARDS",
]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


@dataclass(frozen=True)
class DeploymentRunbookPolicy:
    review_only: bool = True
    deployment_execution_enabled: bool = False
    server_deployment_performed: bool = False
    process_start_enabled: bool = False
    process_stop_enabled: bool = False
    process_restart_enabled: bool = False
    systemd_write_enabled: bool = False
    docker_run_enabled: bool = False
    env_file_write_enabled: bool = False
    secret_injection_metadata_only: bool = True
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    live_trading_enabled: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False
    telegram_send_enabled: bool = False
    external_notification_sent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unsafe_flags(policy: DeploymentRunbookPolicy, sources: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    return {
        "deployment_execution_enabled": policy.deployment_execution_enabled or any(_bool(src.get("deployment_execution_enabled")) for src in sources),
        "server_deployment_performed": policy.server_deployment_performed or any(_bool(src.get("server_deployment_performed")) for src in sources),
        "process_start_enabled": policy.process_start_enabled or any(_bool(src.get("process_start_enabled")) for src in sources),
        "process_stop_enabled": policy.process_stop_enabled or any(_bool(src.get("process_stop_enabled")) for src in sources),
        "process_restart_enabled": policy.process_restart_enabled or any(_bool(src.get("process_restart_enabled")) for src in sources),
        "systemd_write_enabled": policy.systemd_write_enabled or any(_bool(src.get("systemd_write_enabled")) for src in sources),
        "docker_run_enabled": policy.docker_run_enabled or any(_bool(src.get("docker_run_enabled")) for src in sources),
        "env_file_write_enabled": policy.env_file_write_enabled or any(_bool(src.get("env_file_write_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "live_order_submission_allowed": policy.live_order_submission_allowed or any(_bool(src.get("live_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_bool(src.get("external_order_submission_allowed")) for src in sources),
        "external_order_submission_performed": policy.external_order_submission_performed or any(_bool(src.get("external_order_submission_performed")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_bool(src.get("cancel_order_enabled")) for src in sources),
        "live_trading_enabled": policy.live_trading_enabled or any(_bool(src.get("live_trading_enabled")) for src in sources),
        "runtime_settings_mutated": policy.runtime_settings_mutated or any(_bool(src.get("runtime_settings_mutated")) for src in sources),
        "score_weights_mutated": policy.score_weights_mutated or any(_bool(src.get("score_weights_mutated")) for src in sources),
        "auto_promotion_allowed": policy.auto_promotion_allowed or any(_bool(src.get("auto_promotion_allowed")) for src in sources),
        "telegram_send_enabled": policy.telegram_send_enabled or any(_bool(src.get("telegram_send_enabled")) for src in sources),
        "external_notification_sent": policy.external_notification_sent or any(_bool(src.get("external_notification_sent")) for src in sources),
    }


def _default_sections() -> list[dict[str, Any]]:
    return [
        {
            "section_id": "ENVIRONMENT_SETUP",
            "title": "Environment setup",
            "items": [
                "Use a clean server or container with Python dependencies installed from the locked project package.",
                "Set APP_ENV to review_only or paper_preparation unless a later signed approval explicitly changes the stage.",
                "Run compileall and focused regression before any process start is considered.",
            ],
        },
        {
            "section_id": "METADATA_ONLY_SECRET_INJECTION",
            "title": "Metadata-only secret injection policy",
            "items": [
                "Store only secret_reference_id, key_fingerprint_sha256, venue, environment, scope, and operator_id metadata.",
                "Do not write API key values, API secret values, passphrases, or secret files from this runbook.",
                "Live or testnet key values must never be printed, copied into artifacts, or hashed from raw bytes inside this system.",
            ],
        },
        {
            "section_id": "PROCESS_START_STOP",
            "title": "Process start / stop procedure",
            "items": [
                "Start command remains documentation-only until a later explicit deployment approval.",
                "Stop procedure must terminate the process, preserve logs, and leave kill switch state visible.",
                "Restart requires a fresh health check, registry integrity check, and operator review.",
            ],
        },
        {
            "section_id": "MANUAL_KILL_SWITCH",
            "title": "Manual kill switch",
            "items": [
                "The kill switch must fail closed and be checked before testnet/live execution stages.",
                "A kill switch active state blocks order intent, order submission, and live canary promotion.",
                "Operator notes must be captured in review-only evidence before any later restart.",
            ],
        },
        {
            "section_id": "LOG_PATHS",
            "title": "Log paths",
            "items": [
                "Write runtime health and review evidence under storage/latest and append-only registries under storage/registries.",
                "Do not store secrets in logs or exception traces.",
                "Preserve full ID chain references in every operational log summary.",
            ],
        },
        {
            "section_id": "BACKUP_PATHS",
            "title": "Backup paths",
            "items": [
                "Back up source handoff ZIPs, validation bundles, reports, and registries separately.",
                "Never auto-regenerate missing approval, settings, or source files as a backup strategy.",
                "Damaged approval or registry evidence must fail closed and be reviewed manually.",
            ],
        },
        {
            "section_id": "INCIDENT_RESPONSE",
            "title": "Incident response",
            "items": [
                "Trigger incident review on API error spikes, reconciliation mismatch, stale data, daily loss breach, or kill switch activation.",
                "Freeze promotion and order submission until incident evidence is reviewed.",
                "Record incident summary, root cause, affected IDs, and next action in review-only artifacts.",
            ],
        },
        {
            "section_id": "ROLLBACK",
            "title": "Rollback",
            "items": [
                "Rollback uses prior source handoff ZIP and validation bundle hashes, not ad-hoc file edits.",
                "Runtime-impacting rollback requires the same manual approval chain as promotion.",
                "Settings write preview may show rollback diffs, but this runbook must not apply them.",
            ],
        },
        {
            "section_id": "DAILY_REVIEW",
            "title": "Daily review",
            "items": [
                "Review data health, Signal QA, risk gate results, reconciliation blockers, outcome analytics, and monitoring alerts.",
                "Confirm no external order submission, secret access, or runtime mutation occurred unexpectedly.",
                "Summarize next action as repeat_in_paper, expand_test_coverage, block_promotion, or archive.",
            ],
        },
        {
            "section_id": "DISABLED_RUNTIME_GUARDS",
            "title": "Disabled runtime guards",
            "items": [
                "live_trading_enabled, place_order_enabled, cancel_order_enabled, signed_order_executor_enabled, and external_order_submission_allowed remain false.",
                "settings.yaml mutation, score_weights mutation, and automatic promotion remain disabled.",
                "This runbook is review-only and does not deploy, start, stop, or mutate runtime services.",
            ],
        },
    ]


def render_deployment_runbook_markdown(runbook: Mapping[str, Any]) -> str:
    lines = [
        "# Step317 Deployment Runbook",
        "",
        f"Runbook ID: `{runbook.get('deployment_runbook_id')}`",
        f"Status: `{runbook.get('status')}`",
        f"Created at UTC: `{runbook.get('created_at_utc')}`",
        "",
        "This document is review-only. It does not deploy services, start processes, write secret files, mutate settings, submit orders, or promote stages.",
        "",
    ]
    for section in runbook.get("sections", []):
        lines.append(f"## {section.get('title')}")
        lines.append("")
        for item in section.get("items", []):
            lines.append(f"- {item}")
        lines.append("")
    lines.extend([
        "## Safety flags",
        "",
    ])
    for key, value in sorted((runbook.get("safety_flags") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Block reasons")
    lines.append("")
    for reason in runbook.get("blocked_reasons", []):
        lines.append(f"- `{reason}`")
    if not runbook.get("blocked_reasons"):
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def build_deployment_runbook(
    *,
    monitoring_alerting: Mapping[str, Any] | None = None,
    policy: DeploymentRunbookPolicy | None = None,
    sections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    monitoring = dict(monitoring_alerting or {})
    policy = policy or DeploymentRunbookPolicy()
    section_list = [dict(section) for section in (sections or _default_sections())]
    section_ids = [str(section.get("section_id")) for section in section_list]
    missing_sections = [section_id for section_id in REQUIRED_SECTION_IDS if section_id not in section_ids]
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    sources = [monitoring]
    unsafe_flags = _unsafe_flags(policy, sources)
    if any(unsafe_flags.values()):
        blocked_reasons.append(BLOCK_UNSAFE_SIDE_EFFECT)
    if any(unsafe_flags[name] for name in ["deployment_execution_enabled", "server_deployment_performed", "systemd_write_enabled", "docker_run_enabled"]):
        blocked_reasons.append(BLOCK_DEPLOYMENT_EXECUTION_ATTEMPT)
    if any(unsafe_flags[name] for name in ["process_start_enabled", "process_stop_enabled", "process_restart_enabled"]):
        blocked_reasons.append(BLOCK_PROCESS_CONTROL_ATTEMPT)
    if any(unsafe_flags[name] for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blocked_reasons.append(BLOCK_SECRET_VALUE_ACCESS)
    if any(unsafe_flags[name] for name in ["runtime_settings_mutated", "score_weights_mutated", "auto_promotion_allowed"]):
        blocked_reasons.append(BLOCK_RUNTIME_MUTATION)
    if any(unsafe_flags[name] for name in ["live_order_submission_allowed", "external_order_submission_allowed", "external_order_submission_performed", "place_order_enabled", "cancel_order_enabled", "live_trading_enabled"]):
        blocked_reasons.append(BLOCK_LIVE_EXECUTION)
    if any(unsafe_flags[name] for name in ["telegram_send_enabled", "external_notification_sent"]):
        blocked_reasons.append(BLOCK_NOTIFICATION_SEND_ATTEMPT)
    if missing_sections:
        warnings.append("DEPLOYMENT_RUNBOOK_MISSING_RECOMMENDED_SECTIONS")
    if not monitoring:
        warnings.append("MONITORING_ALERTING_EVIDENCE_NOT_ATTACHED")

    safety_flags = {
        "deployment_execution_enabled": False,
        "server_deployment_performed": False,
        "process_start_enabled": False,
        "process_stop_enabled": False,
        "process_restart_enabled": False,
        "systemd_write_enabled": False,
        "docker_run_enabled": False,
        "env_file_write_enabled": False,
        "secret_injection_metadata_only": True,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "live_trading_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "telegram_send_enabled": False,
        "external_notification_sent": False,
    }
    report_id_source = {
        "version": STEP317_DEPLOYMENT_RUNBOOK_VERSION,
        "sections": section_ids,
        "monitoring_alerting_report_id": monitoring.get("monitoring_alerting_report_id"),
        "blocked_reasons": sorted(set(blocked_reasons)),
        "warnings": warnings,
    }
    runbook = {
        "deployment_runbook_id": stable_id("step317_deployment_runbook", report_id_source, 24),
        "deployment_runbook_version": STEP317_DEPLOYMENT_RUNBOOK_VERSION,
        "status": STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if blocked_reasons else STATUS_RECORDED_REVIEW_ONLY,
        "review_only": True,
        "deployment_ready": False,
        "live_canary_deployment_ready": False,
        "live_scaled_deployment_ready": False,
        "monitoring_alerting_report_id": monitoring.get("monitoring_alerting_report_id"),
        "monitoring_alerting_status": monitoring.get("status"),
        "monitoring_alerting_alert_count": monitoring.get("alert_count"),
        "sections": section_list,
        "required_section_ids": list(REQUIRED_SECTION_IDS),
        "missing_required_section_ids": missing_sections,
        "blocked_reasons": sorted(set(blocked_reasons)),
        "warnings": warnings,
        "unsafe_flags_detected": unsafe_flags,
        "safety_flags": safety_flags,
        **safety_flags,
        "created_at_utc": utc_now_canonical(),
    }
    runbook["deployment_runbook_markdown"] = render_deployment_runbook_markdown(runbook)
    runbook["deployment_runbook_sha256"] = sha256_json(_drop_hashes(runbook, "deployment_runbook_sha256"))
    return runbook


def build_deployment_runbook_registry_record(runbook: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(runbook)
    record = {
        "deployment_runbook_id": data.get("deployment_runbook_id"),
        "deployment_runbook_sha256": data.get("deployment_runbook_sha256"),
        "status": data.get("status"),
        "review_only": True,
        "deployment_ready": False,
        "live_canary_deployment_ready": False,
        "live_scaled_deployment_ready": False,
        "monitoring_alerting_report_id": data.get("monitoring_alerting_report_id"),
        "section_count": len(data.get("sections") or []),
        "blocked_reasons": list(data.get("blocked_reasons") or []),
        "warnings": list(data.get("warnings") or []),
        "deployment_execution_enabled": False,
        "server_deployment_performed": False,
        "process_start_enabled": False,
        "secret_file_access_allowed": False,
        "live_order_submission_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": data.get("created_at_utc") or utc_now_canonical(),
    }
    record["deployment_runbook_registry_record_id"] = stable_id("step317_deployment_runbook_registry", record, 24)
    record["deployment_runbook_registry_record_sha256"] = sha256_json(record)
    return record


def persist_deployment_runbook(cfg: AppConfig, runbook: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / "storage" / "latest"
    runbook_dir = cfg.root / "storage" / "deployment_runbook"
    docs_dir = cfg.root / "docs"
    latest_dir.mkdir(parents=True, exist_ok=True)
    runbook_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    payload = dict(runbook)
    markdown = str(payload.get("deployment_runbook_markdown") or render_deployment_runbook_markdown(payload))
    registry_record = build_deployment_runbook_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, DEPLOYMENT_RUNBOOK_REGISTRY_NAME),
        registry_record,
        registry_name=DEPLOYMENT_RUNBOOK_REGISTRY_NAME,
        id_field="deployment_runbook_registry_record_id",
        hash_field="deployment_runbook_registry_record_sha256",
        id_prefix="step317_deployment_runbook_registry",
    )
    payload["deployment_runbook_registry_record_id"] = persisted.get("deployment_runbook_registry_record_id")
    payload["deployment_runbook_registry_record_sha256"] = persisted.get("deployment_runbook_registry_record_sha256")
    payload["deployment_runbook_path"] = str(runbook_dir / "DEPLOYMENT_RUNBOOK_STEP317.md")
    payload["deployment_runbook_latest_path"] = str(latest_dir / "deployment_runbook_manifest.json")
    atomic_write_json(latest_dir / "deployment_runbook_manifest.json", {k: v for k, v in payload.items() if k != "deployment_runbook_markdown"})
    atomic_write_json(latest_dir / "deployment_runbook_registry_record.json", persisted)
    atomic_write_json(runbook_dir / "deployment_runbook_manifest.json", {k: v for k, v in payload.items() if k != "deployment_runbook_markdown"})
    (runbook_dir / "DEPLOYMENT_RUNBOOK_STEP317.md").write_text(markdown, encoding="utf-8")
    (docs_dir / "DEPLOYMENT_RUNBOOK_STEP317.md").write_text(markdown, encoding="utf-8")
    return payload


def run_deployment_runbook_latest(
    project_root: str | Path | None = None,
    *,
    monitoring_alerting: Mapping[str, Any] | None = None,
    policy: DeploymentRunbookPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    latest = cfg.root / "storage" / "latest"
    monitoring = dict(monitoring_alerting or read_json(latest / "monitoring_alerting_report.json", default={}) or {})
    runbook = build_deployment_runbook(monitoring_alerting=monitoring, policy=policy)
    return persist_deployment_runbook(cfg, runbook)
