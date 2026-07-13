from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    PROMOTION_BLOCKER_NONE,
    STATUS_RECONCILED,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP310_SIGNED_TESTNET_SESSION_CLOSE_REPORT_VERSION = "step310_signed_testnet_session_close_report_v1"
SIGNED_TESTNET_SESSION_CLOSE_REPORT_REGISTRY_NAME = "signed_testnet_session_close_report_registry"

STATUS_RECORDED_REVIEW_ONLY = "SIGNED_TESTNET_SESSION_CLOSE_REPORT_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED = "SIGNED_TESTNET_SESSION_CLOSE_REPORT_BLOCKED"
STATUS_BLOCKED_EVIDENCE_MISSING = "SIGNED_TESTNET_SESSION_CLOSE_REPORT_BLOCKED_EVIDENCE_MISSING"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "SIGNED_TESTNET_SESSION_CLOSE_REPORT_BLOCKED_UNSAFE_SIDE_EFFECT"

RECOMMEND_REPEAT_SIGNED_TESTNET_PREPARATION = "repeat_signed_testnet_preparation"
RECOMMEND_EXPAND_TESTNET_VALIDATION = "expand_signed_testnet_validation"
RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION = "block_signed_testnet_promotion"
RECOMMEND_ARCHIVE_SESSION = "archive_session"

BLOCK_MISSING_RECONCILIATION = "STEP310_BLOCK_MISSING_SIGNED_TESTNET_RECONCILIATION"
BLOCK_MISSING_EXECUTION_RECORD = "STEP310_BLOCK_MISSING_SIGNED_TESTNET_EXECUTION_RECORD"
BLOCK_RECONCILIATION_PROMOTION_BLOCKED = "STEP310_BLOCK_RECONCILIATION_PROMOTION_BLOCKED"
BLOCK_RECONCILIATION_MISMATCH = "STEP310_BLOCK_RECONCILIATION_MISMATCH"
BLOCK_EXECUTION_NOT_SUBMITTED = "STEP310_BLOCK_EXECUTION_NOT_SUBMITTED"
BLOCK_UNSAFE_SIDE_EFFECT = "STEP310_BLOCK_UNSAFE_SIDE_EFFECT"
BLOCK_SECRET_VALUE_ACCESS = "STEP310_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_RUNTIME_MUTATION = "STEP310_BLOCK_RUNTIME_MUTATION"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


def _numeric(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary(values: Sequence[Any]) -> dict[str, Any]:
    numeric_values = [v for v in (_numeric(value) for value in values) if v is not None]
    if not numeric_values:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(numeric_values),
        "min": min(numeric_values),
        "max": max(numeric_values),
        "avg": mean(numeric_values),
    }


@dataclass(frozen=True)
class SignedTestnetSessionClosePolicy:
    review_only: bool = True
    require_reconciliation_record: bool = True
    require_execution_record: bool = True
    require_zero_reconciliation_mismatch_for_promotion: bool = True
    require_no_unsafe_side_effect: bool = True
    allow_signed_testnet_promotion: bool = False
    ready_for_signed_testnet_execution: bool = False
    testnet_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    signed_order_executor_enabled: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    live_trading_allowed_by_this_module: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unsafe_side_effects(
    *,
    execution_record: Mapping[str, Any],
    reconciliation_record: Mapping[str, Any],
    policy: SignedTestnetSessionClosePolicy,
) -> dict[str, bool]:
    sources = [execution_record, reconciliation_record]
    return {
        "ready_for_signed_testnet_execution": policy.ready_for_signed_testnet_execution or any(_bool(src.get("ready_for_signed_testnet_execution")) for src in sources),
        "testnet_order_submission_allowed": policy.testnet_order_submission_allowed or any(_bool(src.get("testnet_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_bool(src.get("external_order_submission_allowed")) for src in sources),
        "external_order_submission_performed": policy.external_order_submission_performed or any(_bool(src.get("external_order_submission_performed")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_bool(src.get("cancel_order_enabled")) for src in sources),
        "signed_order_executor_enabled": policy.signed_order_executor_enabled or any(_bool(src.get("signed_order_executor_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "live_trading_allowed_by_this_module": policy.live_trading_allowed_by_this_module or any(_bool(src.get("live_trading_allowed_by_this_module")) for src in sources),
        "runtime_settings_mutated": policy.runtime_settings_mutated or any(_bool(src.get("runtime_settings_mutated")) for src in sources),
        "score_weights_mutated": policy.score_weights_mutated or any(_bool(src.get("score_weights_mutated")) for src in sources),
        "auto_promotion_allowed": policy.auto_promotion_allowed or any(_bool(src.get("auto_promotion_allowed")) for src in sources),
    }


def _execution_metrics(execution_record: Mapping[str, Any]) -> dict[str, Any]:
    submitted = _bool(execution_record.get("submitted_to_exchange"))
    status = _text(execution_record.get("status"))
    exchange_status = _text(execution_record.get("exchange_status") or execution_record.get("fetched_status") or execution_record.get("state"))
    filled = submitted and exchange_status.upper() in {"FILLED", "SIGNED_TESTNET_SUBMITTED", "PARTIALLY_FILLED"}
    rejected = (not submitted) or status.startswith("NO_") or "REJECTED" in exchange_status.upper() or "BLOCKED" in exchange_status.upper()
    return {
        "orders_submitted_count": 1 if submitted else 0,
        "orders_filled_count": 1 if filled else 0,
        "orders_rejected_count": 1 if rejected else 0,
        "orders_not_submitted_count": 0 if submitted else 1,
        "exchange_order_ids": [_text(execution_record.get("exchange_order_id"))] if submitted and _text(execution_record.get("exchange_order_id")) else [],
        "latency_values_ms": [execution_record.get("latency_ms"), execution_record.get("fill_latency_ms")],
        "slippage_values": [execution_record.get("slippage"), execution_record.get("slippage_bps")],
        "api_error_count": int(_bool(execution_record.get("api_error"))) + len(_list(execution_record.get("api_errors"))),
        "manual_override_count": int(_bool(execution_record.get("manual_override"))) + len(_list(execution_record.get("manual_overrides"))),
    }


def build_signed_testnet_session_close_report(
    *,
    execution_record: Mapping[str, Any] | None,
    reconciliation_record: Mapping[str, Any] | None,
    pre_submit_validation_report: Mapping[str, Any] | None = None,
    venue_probe: Mapping[str, Any] | None = None,
    enablement_packet: Mapping[str, Any] | None = None,
    policy: SignedTestnetSessionClosePolicy | None = None,
) -> dict[str, Any]:
    execution = dict(execution_record or {})
    reconciliation = dict(reconciliation_record or {})
    pre_submit = dict(pre_submit_validation_report or {})
    probe = dict(venue_probe or {})
    enablement = dict(enablement_packet or {})
    policy = policy or SignedTestnetSessionClosePolicy()
    blockers: list[str] = []
    warnings: list[str] = []

    if not reconciliation:
        blockers.append(BLOCK_MISSING_RECONCILIATION)
    if not execution:
        blockers.append(BLOCK_MISSING_EXECUTION_RECORD)

    unsafe_flags = _unsafe_side_effects(execution_record=execution, reconciliation_record=reconciliation, policy=policy)
    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_SIDE_EFFECT)
    if any(unsafe_flags[name] for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)
    if any(unsafe_flags[name] for name in ["runtime_settings_mutated", "score_weights_mutated", "auto_promotion_allowed"]):
        blockers.append(BLOCK_RUNTIME_MUTATION)

    promotion_blocker = reconciliation.get("promotion_blocker")
    reconciliation_status = _text(reconciliation.get("status") or reconciliation.get("reconciliation_status"))
    if reconciliation and reconciliation.get("promotion_blocked") is True:
        blockers.append(BLOCK_RECONCILIATION_PROMOTION_BLOCKED)
    if reconciliation_status and reconciliation_status != STATUS_RECONCILED:
        if "MISMATCH" in reconciliation_status:
            blockers.append(BLOCK_RECONCILIATION_MISMATCH)
        elif promotion_blocker != PROMOTION_BLOCKER_NONE:
            blockers.append(BLOCK_RECONCILIATION_PROMOTION_BLOCKED)
    if execution and not _bool(execution.get("submitted_to_exchange")):
        blockers.append(BLOCK_EXECUTION_NOT_SUBMITTED)

    metrics = _execution_metrics(execution)
    reconciliation_mismatch_count = 1 if "MISMATCH" in reconciliation_status or BLOCK_RECONCILIATION_MISMATCH in blockers else 0
    if not reconciliation and policy.require_reconciliation_record:
        reconciliation_mismatch_count = 1
    api_error_count = int(metrics["api_error_count"])
    manual_override_count = int(metrics["manual_override_count"])

    latency_summary = _summary(metrics.pop("latency_values_ms"))
    slippage_summary = _summary(metrics.pop("slippage_values"))

    if blockers:
        status = STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if BLOCK_UNSAFE_SIDE_EFFECT in blockers else STATUS_BLOCKED
        if BLOCK_MISSING_RECONCILIATION in blockers or BLOCK_MISSING_EXECUTION_RECORD in blockers:
            status = STATUS_BLOCKED_EVIDENCE_MISSING
        promotion_recommendation = RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION
    else:
        status = STATUS_RECORDED_REVIEW_ONLY
        promotion_recommendation = RECOMMEND_EXPAND_TESTNET_VALIDATION if metrics["orders_submitted_count"] else RECOMMEND_REPEAT_SIGNED_TESTNET_PREPARATION

    session_id_source = {
        "execution_id": execution.get("execution_id"),
        "reconciliation_id": reconciliation.get("reconciliation_id"),
        "status": status,
        "promotion_recommendation": promotion_recommendation,
    }
    report = {
        "version": STEP310_SIGNED_TESTNET_SESSION_CLOSE_REPORT_VERSION,
        "signed_testnet_session_close_report_id": stable_id("step310_signed_testnet_session_close_report", session_id_source, 24),
        "signed_testnet_session_id": stable_id("step310_signed_testnet_session", session_id_source, 24),
        "status": status,
        "closed_review_only": True,
        "session_closed": True,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "promotion_recommendation": promotion_recommendation,
        "signed_testnet_promotion_allowed_by_this_module": False,
        "testnet_order_submission_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "execution_id": execution.get("execution_id"),
        "order_intent_id": execution.get("order_intent_id") or reconciliation.get("order_intent_id"),
        "decision_id": execution.get("decision_id") or reconciliation.get("decision_id"),
        "risk_gate_id": execution.get("risk_gate_id") or reconciliation.get("risk_gate_id"),
        "research_signal_id": execution.get("research_signal_id") or reconciliation.get("research_signal_id"),
        "profile_id": execution.get("profile_id") or reconciliation.get("profile_id"),
        "idempotency_key": execution.get("idempotency_key") or reconciliation.get("idempotency_key"),
        "exchange_order_ids": metrics["exchange_order_ids"],
        "reconciliation_id": reconciliation.get("reconciliation_id"),
        "reconciliation_status": reconciliation_status or None,
        "reconciliation_promotion_blocker": promotion_blocker,
        "reconciliation_mismatch_count": reconciliation_mismatch_count,
        "orders_submitted_count": metrics["orders_submitted_count"],
        "orders_filled_count": metrics["orders_filled_count"],
        "orders_rejected_count": metrics["orders_rejected_count"],
        "orders_not_submitted_count": metrics["orders_not_submitted_count"],
        "api_error_count": api_error_count,
        "latency_summary": latency_summary,
        "slippage_summary": slippage_summary,
        "manual_override_count": manual_override_count,
        "pre_submit_validation_id": pre_submit.get("signed_testnet_pre_submit_validation_id"),
        "pre_submit_status": pre_submit.get("status"),
        "venue_probe_id": probe.get("real_read_only_venue_probe_id") or probe.get("venue_probe_id"),
        "venue_probe_status": probe.get("status"),
        "enablement_packet_id": enablement.get("signed_testnet_execution_enablement_packet_id"),
        "enablement_status": enablement.get("status"),
        "canonical_id_chain": dict(execution.get("canonical_id_chain") or reconciliation.get("canonical_id_chain") or {}),
        "missing_canonical_id_fields": list(execution.get("missing_canonical_id_fields") or reconciliation.get("missing_canonical_id_fields") or []),
        "unsafe_side_effect_evidence": unsafe_flags,
        "policy": policy.to_dict(),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["signed_testnet_session_close_report_sha256"] = sha256_json(_drop_hashes(report, "signed_testnet_session_close_report_sha256"))
    return report


def build_signed_testnet_session_close_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    record = {
        "version": STEP310_SIGNED_TESTNET_SESSION_CLOSE_REPORT_VERSION,
        "signed_testnet_session_close_report_id": data.get("signed_testnet_session_close_report_id"),
        "signed_testnet_session_id": data.get("signed_testnet_session_id"),
        "signed_testnet_session_close_report_sha256": data.get("signed_testnet_session_close_report_sha256"),
        "status": data.get("status"),
        "promotion_recommendation": data.get("promotion_recommendation"),
        "signed_testnet_promotion_allowed_by_this_module": False,
        "orders_submitted_count": data.get("orders_submitted_count", 0),
        "orders_filled_count": data.get("orders_filled_count", 0),
        "orders_rejected_count": data.get("orders_rejected_count", 0),
        "orders_not_submitted_count": data.get("orders_not_submitted_count", 0),
        "reconciliation_mismatch_count": data.get("reconciliation_mismatch_count", 0),
        "api_error_count": data.get("api_error_count", 0),
        "manual_override_count": data.get("manual_override_count", 0),
        "execution_id": data.get("execution_id"),
        "reconciliation_id": data.get("reconciliation_id"),
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "block_reasons": list(data.get("block_reasons") or []),
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_session_close_registry_record_id"] = stable_id("step310_signed_testnet_session_close_registry", record, 24)
    record["signed_testnet_session_close_registry_record_sha256"] = sha256_json(record)
    return record


def persist_signed_testnet_session_close_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    session_dir = cfg.root / "storage" / "signed_testnet_session_close"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    registry_record = build_signed_testnet_session_close_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, SIGNED_TESTNET_SESSION_CLOSE_REPORT_REGISTRY_NAME),
        registry_record,
        registry_name=SIGNED_TESTNET_SESSION_CLOSE_REPORT_REGISTRY_NAME,
        id_field="signed_testnet_session_close_registry_record_id",
        hash_field="signed_testnet_session_close_registry_record_sha256",
        id_prefix="step310_signed_testnet_session_close_registry",
    )
    payload["signed_testnet_session_close_registry_record_id"] = persisted.get("signed_testnet_session_close_registry_record_id")
    payload["signed_testnet_session_close_registry_record_sha256"] = persisted.get("signed_testnet_session_close_registry_record_sha256")
    atomic_write_json(latest_dir / "signed_testnet_session_close_report.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_session_close_registry_record.json", persisted)
    atomic_write_json(session_dir / "signed_testnet_session_close_report.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_signed_testnet_session_close_report_latest(
    *,
    project_root: str | Path = ".",
    execution_record: Mapping[str, Any] | None = None,
    reconciliation_record: Mapping[str, Any] | None = None,
    pre_submit_validation_report: Mapping[str, Any] | None = None,
    venue_probe: Mapping[str, Any] | None = None,
    enablement_packet: Mapping[str, Any] | None = None,
    policy: SignedTestnetSessionClosePolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    execution = dict(execution_record or _latest_json(latest_dir / "signed_testnet_order_execution_record.json"))
    reconciliation = dict(reconciliation_record or _latest_json(latest_dir / "signed_testnet_reconciliation_record.json"))
    pre_submit = dict(pre_submit_validation_report or _latest_json(latest_dir / "signed_testnet_pre_submit_validation_report.json"))
    probe = dict(venue_probe or _latest_json(latest_dir / "real_read_only_venue_probe.json"))
    enablement = dict(enablement_packet or _latest_json(latest_dir / "signed_testnet_execution_enablement_packet.json"))
    report = build_signed_testnet_session_close_report(
        execution_record=execution,
        reconciliation_record=reconciliation,
        pre_submit_validation_report=pre_submit,
        venue_probe=probe,
        enablement_packet=enablement,
        policy=policy,
    )
    return persist_signed_testnet_session_close_report(cfg, report)
