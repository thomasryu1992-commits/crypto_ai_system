from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP316_MONITORING_ALERTING_VERSION = "step316_monitoring_alerting_v1"
MONITORING_ALERTING_REGISTRY_NAME = "monitoring_alerting_registry"

STATUS_RECORDED_REVIEW_ONLY = "MONITORING_ALERTING_REVIEW_ONLY_RECORDED"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "MONITORING_ALERTING_BLOCKED_UNSAFE_SIDE_EFFECT"

ALERT_HEARTBEAT = "HEARTBEAT_REVIEW_ONLY"
ALERT_DATA_HEALTH = "DATA_HEALTH_ALERT"
ALERT_ORDER_SUBMISSION_BLOCKED = "ORDER_SUBMISSION_BLOCKED_ALERT"
ALERT_SIGNED_TESTNET_RECONCILIATION = "SIGNED_TESTNET_RECONCILIATION_BLOCKER_ALERT"
ALERT_LIVE_CANARY_RECONCILIATION = "LIVE_CANARY_RECONCILIATION_BLOCKER_ALERT"
ALERT_DAILY_LOSS = "DAILY_LOSS_ALERT"
ALERT_KILL_SWITCH = "KILL_SWITCH_ALERT"
ALERT_API_ERROR = "API_ERROR_ALERT"
ALERT_MONITORING_REVIEW_ONLY = "MONITORING_REVIEW_ONLY_ALERT"

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

BLOCK_UNSAFE_SIDE_EFFECT = "STEP316_BLOCK_UNSAFE_SIDE_EFFECT"
BLOCK_NOTIFICATION_SEND_ATTEMPT = "STEP316_BLOCK_NOTIFICATION_SEND_ATTEMPT"
BLOCK_RUNTIME_MUTATION = "STEP316_BLOCK_RUNTIME_MUTATION"
BLOCK_SECRET_VALUE_ACCESS = "STEP316_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_LIVE_EXECUTION = "STEP316_BLOCK_LIVE_EXECUTION"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _numeric(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


@dataclass(frozen=True)
class MonitoringAlertingPolicy:
    review_only: bool = True
    heartbeat_required: bool = True
    monitor_data_freshness: bool = True
    monitor_order_submission_blocks: bool = True
    monitor_reconciliation_blockers: bool = True
    monitor_daily_loss: bool = True
    monitor_kill_switch: bool = True
    monitor_api_errors: bool = True
    telegram_send_enabled: bool = False
    telegram_message_sent: bool = False
    external_notification_sent: bool = False
    webhook_called: bool = False
    email_sent: bool = False
    live_trading_enabled: bool = False
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unsafe_side_effects(policy: MonitoringAlertingPolicy, sources: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    return {
        "telegram_send_enabled": policy.telegram_send_enabled or any(_bool(src.get("telegram_send_enabled")) for src in sources),
        "telegram_message_sent": policy.telegram_message_sent or any(_bool(src.get("telegram_message_sent")) for src in sources),
        "external_notification_sent": policy.external_notification_sent or any(_bool(src.get("external_notification_sent")) for src in sources),
        "webhook_called": policy.webhook_called or any(_bool(src.get("webhook_called")) for src in sources),
        "email_sent": policy.email_sent or any(_bool(src.get("email_sent")) for src in sources),
        "live_trading_enabled": policy.live_trading_enabled or any(_bool(src.get("live_trading_enabled")) for src in sources),
        "live_order_submission_allowed": policy.live_order_submission_allowed or any(_bool(src.get("live_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_bool(src.get("external_order_submission_allowed")) for src in sources),
        "external_order_submission_performed": policy.external_order_submission_performed or any(_bool(src.get("external_order_submission_performed")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_bool(src.get("cancel_order_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "runtime_settings_mutated": policy.runtime_settings_mutated or any(_bool(src.get("runtime_settings_mutated")) for src in sources),
        "score_weights_mutated": policy.score_weights_mutated or any(_bool(src.get("score_weights_mutated")) for src in sources),
        "auto_promotion_allowed": policy.auto_promotion_allowed or any(_bool(src.get("auto_promotion_allowed")) for src in sources),
    }


def _alert(alert_type: str, severity: str, title: str, message: str, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "message": message,
        "evidence": dict(evidence or {}),
        "review_only": True,
        "external_notification_sent": False,
        "telegram_message_sent": False,
        "created_at_utc": utc_now_canonical(),
    }


def build_monitoring_alerts(
    *,
    data_health: Mapping[str, Any] | None = None,
    risk_guard: Mapping[str, Any] | None = None,
    order: Mapping[str, Any] | None = None,
    signed_testnet_reconciliation: Mapping[str, Any] | None = None,
    signed_testnet_session_close: Mapping[str, Any] | None = None,
    live_canary_order_executor: Mapping[str, Any] | None = None,
    live_canary_reconciliation: Mapping[str, Any] | None = None,
    policy: MonitoringAlertingPolicy | None = None,
) -> list[dict[str, Any]]:
    policy = policy or MonitoringAlertingPolicy()
    data = dict(data_health or {})
    risk = dict(risk_guard or {})
    order_record = dict(order or {})
    signed_rec = dict(signed_testnet_reconciliation or {})
    signed_close = dict(signed_testnet_session_close or {})
    live_exec = dict(live_canary_order_executor or {})
    live_rec = dict(live_canary_reconciliation or {})
    alerts: list[dict[str, Any]] = []

    if policy.heartbeat_required:
        alerts.append(_alert(ALERT_HEARTBEAT, SEVERITY_INFO, "Monitoring heartbeat recorded", "Review-only monitoring heartbeat was generated.", {"heartbeat_ok": True}))

    data_status = _text(data.get("status"))
    if policy.monitor_data_freshness and data_status and data_status not in {"HEALTHY", "VALID", "PASS", "OK"}:
        alerts.append(_alert(ALERT_DATA_HEALTH, SEVERITY_WARNING, "Data health is not eligible for execution", f"Data health status is {data_status}.", {"data_health_status": data_status, "allow_trading": data.get("allow_trading")}))

    order_status = _text(order_record.get("status"))
    live_exec_status = _text(live_exec.get("status"))
    if policy.monitor_order_submission_blocks:
        if order_status.startswith("NO_") or "BLOCK" in order_status or order_record.get("order_intent_created") is False:
            alerts.append(_alert(ALERT_ORDER_SUBMISSION_BLOCKED, SEVERITY_INFO, "Order submission remains blocked", "Order executor did not create or submit an external order.", {"order_status": order_status, "order_intent_created": order_record.get("order_intent_created")}))
        if live_exec_status.startswith("NO_") or "BLOCK" in live_exec_status or live_exec.get("submitted_to_exchange") is False:
            alerts.append(_alert(ALERT_ORDER_SUBMISSION_BLOCKED, SEVERITY_INFO, "Live canary submission remains blocked", "Live canary executor did not submit an order.", {"live_canary_order_executor_status": live_exec_status, "submitted_to_exchange": live_exec.get("submitted_to_exchange")}))

    if policy.monitor_reconciliation_blockers:
        signed_blocker = _text(signed_rec.get("promotion_blocker") or signed_close.get("promotion_recommendation"))
        signed_status = _text(signed_rec.get("status") or signed_close.get("status"))
        if signed_blocker and signed_blocker not in {"NO_TESTNET_PROMOTION_BLOCKER", "NO_SIGNED_TESTNET_PROMOTION_BLOCKER", "expand_signed_testnet_validation"}:
            alerts.append(_alert(ALERT_SIGNED_TESTNET_RECONCILIATION, SEVERITY_CRITICAL, "Signed testnet promotion is blocked", "Signed testnet reconciliation/session close evidence blocks promotion.", {"status": signed_status, "promotion_blocker": signed_blocker}))
        live_blocker = _text(live_rec.get("promotion_blocker"))
        live_status = _text(live_rec.get("status"))
        if live_blocker and live_blocker != "NO_LIVE_CANARY_PROMOTION_BLOCKER":
            alerts.append(_alert(ALERT_LIVE_CANARY_RECONCILIATION, SEVERITY_CRITICAL, "Live canary promotion is blocked", "Live canary reconciliation evidence blocks promotion.", {"status": live_status, "promotion_blocker": live_blocker}))

    risk_problems = [str(item) for item in _list(risk.get("problems"))]
    if policy.monitor_daily_loss and ("daily_loss_limit_breached" in risk_problems or _numeric(risk.get("daily_pnl_r")) < 0 and _bool(risk.get("daily_loss_lockout"))):
        alerts.append(_alert(ALERT_DAILY_LOSS, SEVERITY_CRITICAL, "Daily loss guard active", "Risk guard reports a daily loss lockout or breach.", {"daily_pnl_r": risk.get("daily_pnl_r"), "problems": risk_problems}))

    if policy.monitor_kill_switch:
        kill_active = any(_bool(src.get("manual_kill_switch_active") or src.get("kill_switch_active")) for src in [risk, order_record, live_exec, live_rec])
        if kill_active:
            alerts.append(_alert(ALERT_KILL_SWITCH, SEVERITY_CRITICAL, "Manual kill switch is active", "A manual kill switch flag is active in monitoring inputs.", {"manual_kill_switch_active": True}))

    if policy.monitor_api_errors:
        api_errors = int(_numeric(signed_close.get("api_error_count"))) + int(_numeric(live_exec.get("api_error_count"))) + int(_numeric(live_rec.get("api_error_count")))
        if api_errors > 0:
            alerts.append(_alert(ALERT_API_ERROR, SEVERITY_WARNING, "API error count detected", "Monitoring inputs report API errors.", {"api_error_count": api_errors}))

    alerts.append(_alert(ALERT_MONITORING_REVIEW_ONLY, SEVERITY_INFO, "Alerts are review-only", "No Telegram, webhook, email, or external alert was sent by this module.", {"telegram_send_enabled": False, "external_notification_sent": False}))
    return alerts


def build_monitoring_alerting_report(
    *,
    data_health: Mapping[str, Any] | None = None,
    risk_guard: Mapping[str, Any] | None = None,
    order: Mapping[str, Any] | None = None,
    signed_testnet_reconciliation: Mapping[str, Any] | None = None,
    signed_testnet_session_close: Mapping[str, Any] | None = None,
    live_canary_order_executor: Mapping[str, Any] | None = None,
    live_canary_reconciliation: Mapping[str, Any] | None = None,
    policy: MonitoringAlertingPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or MonitoringAlertingPolicy()
    sources = [
        dict(data_health or {}),
        dict(risk_guard or {}),
        dict(order or {}),
        dict(signed_testnet_reconciliation or {}),
        dict(signed_testnet_session_close or {}),
        dict(live_canary_order_executor or {}),
        dict(live_canary_reconciliation or {}),
    ]
    alerts = build_monitoring_alerts(
        data_health=data_health,
        risk_guard=risk_guard,
        order=order,
        signed_testnet_reconciliation=signed_testnet_reconciliation,
        signed_testnet_session_close=signed_testnet_session_close,
        live_canary_order_executor=live_canary_order_executor,
        live_canary_reconciliation=live_canary_reconciliation,
        policy=policy,
    )
    unsafe_flags = _unsafe_side_effects(policy, sources)
    blockers: list[str] = []
    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_SIDE_EFFECT)
    if any(unsafe_flags[name] for name in ["telegram_send_enabled", "telegram_message_sent", "external_notification_sent", "webhook_called", "email_sent"]):
        blockers.append(BLOCK_NOTIFICATION_SEND_ATTEMPT)
    if any(unsafe_flags[name] for name in ["runtime_settings_mutated", "score_weights_mutated", "auto_promotion_allowed"]):
        blockers.append(BLOCK_RUNTIME_MUTATION)
    if any(unsafe_flags[name] for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)
    if any(unsafe_flags[name] for name in ["live_trading_enabled", "live_order_submission_allowed", "external_order_submission_allowed", "external_order_submission_performed", "place_order_enabled", "cancel_order_enabled"]):
        blockers.append(BLOCK_LIVE_EXECUTION)

    severity_counts: dict[str, int] = {SEVERITY_INFO: 0, SEVERITY_WARNING: 0, SEVERITY_CRITICAL: 0}
    for item in alerts:
        severity_counts[str(item.get("severity") or SEVERITY_INFO)] = severity_counts.get(str(item.get("severity") or SEVERITY_INFO), 0) + 1

    report_id_source = {
        "alerts": [(a.get("alert_type"), a.get("severity"), a.get("title")) for a in alerts],
        "blockers": sorted(set(blockers)),
    }
    status = STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if blockers else STATUS_RECORDED_REVIEW_ONLY
    report = {
        "version": STEP316_MONITORING_ALERTING_VERSION,
        "monitoring_alerting_report_id": stable_id("step316_monitoring_alerting", report_id_source, 24),
        "status": status,
        "review_only": True,
        "heartbeat_ok": True,
        "alerts": alerts,
        "alert_count": len(alerts),
        "critical_alert_count": severity_counts.get(SEVERITY_CRITICAL, 0),
        "warning_alert_count": severity_counts.get(SEVERITY_WARNING, 0),
        "info_alert_count": severity_counts.get(SEVERITY_INFO, 0),
        "block_reasons": sorted(set(blockers)),
        "unsafe_side_effect_evidence": unsafe_flags,
        "data_health_status": dict(data_health or {}).get("status"),
        "risk_guard_status": dict(risk_guard or {}).get("status"),
        "order_status": dict(order or {}).get("status"),
        "signed_testnet_reconciliation_status": dict(signed_testnet_reconciliation or {}).get("status"),
        "signed_testnet_session_close_status": dict(signed_testnet_session_close or {}).get("status"),
        "live_canary_order_executor_status": dict(live_canary_order_executor or {}).get("status"),
        "live_canary_reconciliation_status": dict(live_canary_reconciliation or {}).get("status"),
        "telegram_send_enabled": False,
        "telegram_message_sent": False,
        "external_notification_sent": False,
        "webhook_called": False,
        "email_sent": False,
        "live_trading_allowed_by_this_module": False,
        "live_order_submission_allowed_by_this_module": False,
        "external_order_submission_allowed_by_this_module": False,
        "external_order_submission_performed_by_this_module": False,
        "place_order_enabled_by_this_module": False,
        "cancel_order_enabled_by_this_module": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["monitoring_alerting_report_sha256"] = sha256_json(_drop_hashes(report, "monitoring_alerting_report_sha256"))
    return report


def build_monitoring_alerting_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    record = {
        "version": STEP316_MONITORING_ALERTING_VERSION,
        "monitoring_alerting_report_id": data.get("monitoring_alerting_report_id"),
        "monitoring_alerting_report_sha256": data.get("monitoring_alerting_report_sha256"),
        "status": data.get("status"),
        "alert_count": data.get("alert_count"),
        "critical_alert_count": data.get("critical_alert_count"),
        "warning_alert_count": data.get("warning_alert_count"),
        "info_alert_count": data.get("info_alert_count"),
        "block_reasons": list(data.get("block_reasons") or []),
        "telegram_message_sent": False,
        "external_notification_sent": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["monitoring_alerting_registry_record_id"] = stable_id("step316_monitoring_alerting_registry", record, 24)
    record["monitoring_alerting_registry_record_sha256"] = sha256_json(record)
    return record


def persist_monitoring_alerting_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    monitoring_dir = cfg.root / "storage" / "monitoring_alerting"
    monitoring_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    registry_record = build_monitoring_alerting_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, MONITORING_ALERTING_REGISTRY_NAME),
        registry_record,
        registry_name=MONITORING_ALERTING_REGISTRY_NAME,
        id_field="monitoring_alerting_registry_record_id",
        hash_field="monitoring_alerting_registry_record_sha256",
        id_prefix="step316_monitoring_alerting_registry",
    )
    payload["monitoring_alerting_registry_record_id"] = persisted.get("monitoring_alerting_registry_record_id")
    payload["monitoring_alerting_registry_record_sha256"] = persisted.get("monitoring_alerting_registry_record_sha256")
    atomic_write_json(latest_dir / "monitoring_alerting_report.json", payload)
    atomic_write_json(latest_dir / "monitoring_alerting_registry_record.json", persisted)
    atomic_write_json(monitoring_dir / "monitoring_alerting_report.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_monitoring_alerting_latest(
    *,
    project_root: str | Path = ".",
    data_health: Mapping[str, Any] | None = None,
    risk_guard: Mapping[str, Any] | None = None,
    order: Mapping[str, Any] | None = None,
    signed_testnet_reconciliation: Mapping[str, Any] | None = None,
    signed_testnet_session_close: Mapping[str, Any] | None = None,
    live_canary_order_executor: Mapping[str, Any] | None = None,
    live_canary_reconciliation: Mapping[str, Any] | None = None,
    policy: MonitoringAlertingPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    report = build_monitoring_alerting_report(
        data_health=data_health or _latest_json(latest_dir / "data_health.json"),
        risk_guard=risk_guard or _latest_json(latest_dir / "risk_status.json"),
        order=order or _latest_json(latest_dir / "order_result.json"),
        signed_testnet_reconciliation=signed_testnet_reconciliation or _latest_json(latest_dir / "signed_testnet_reconciliation_record.json"),
        signed_testnet_session_close=signed_testnet_session_close or _latest_json(latest_dir / "signed_testnet_session_close_report.json"),
        live_canary_order_executor=live_canary_order_executor or _latest_json(latest_dir / "live_canary_order_execution_record.json"),
        live_canary_reconciliation=live_canary_reconciliation or _latest_json(latest_dir / "live_canary_reconciliation_record.json"),
        policy=policy,
    )
    return persist_monitoring_alerting_report(cfg, report)
