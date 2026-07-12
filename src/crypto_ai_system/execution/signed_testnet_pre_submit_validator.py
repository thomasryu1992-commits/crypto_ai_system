from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.real_read_only_venue_probe import run_real_read_only_venue_probe_latest
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json, read_json
from config.settings import ORDER_INTENT_PATH, ORDER_RESULT_PATH, TRADE_DECISION_PATH

STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION = "step306_signed_testnet_pre_submit_validator_v1"
SIGNED_TESTNET_PRE_SUBMIT_REGISTRY_NAME = "signed_testnet_pre_submit_validator_registry"

PRE_SUBMIT_VALIDATED_REVIEW_ONLY = "SIGNED_TESTNET_PRE_SUBMIT_VALIDATED_REVIEW_ONLY"
PRE_SUBMIT_BLOCKED = "SIGNED_TESTNET_PRE_SUBMIT_BLOCKED"

BLOCK_MISSING_ORDER_INTENT = "STEP306_BLOCK_MISSING_ORDER_INTENT"
BLOCK_ORDER_INTENT_NOT_CREATED = "STEP306_BLOCK_ORDER_INTENT_NOT_CREATED"
BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET = "STEP306_BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET"
BLOCK_MISSING_RISK_GATE = "STEP306_BLOCK_MISSING_RISK_GATE"
BLOCK_RISK_GATE_NOT_SIGNED_TESTNET = "STEP306_BLOCK_RISK_GATE_NOT_SIGNED_TESTNET"
BLOCK_RISK_GATE_NOT_APPROVED = "STEP306_BLOCK_RISK_GATE_NOT_APPROVED"
BLOCK_MISSING_VENUE_PROBE = "STEP306_BLOCK_MISSING_VENUE_PROBE"
BLOCK_VENUE_PROBE_INVALID = "STEP306_BLOCK_VENUE_PROBE_INVALID"
BLOCK_VENUE_PROBE_STALE = "STEP306_BLOCK_VENUE_PROBE_STALE"
BLOCK_UNSAFE_SUBMISSION_FLAG = "STEP306_BLOCK_UNSAFE_SUBMISSION_FLAG"
BLOCK_SECRET_VALUE_ACCESS = "STEP306_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_MISSING_CANONICAL_ID_CHAIN = "STEP306_BLOCK_MISSING_CANONICAL_ID_CHAIN"

_REQUIRED_ORDER_FIELDS = ["order_intent_id", "decision_id", "risk_gate_id", "research_signal_id", "profile_id", "symbol", "side"]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _canonical_age_sec(value: Any) -> int | None:
    if not is_canonical_utc_timestamp(value):
        return None
    parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


@dataclass(frozen=True)
class SignedTestnetPreSubmitPolicy:
    review_only: bool = True
    require_order_intent: bool = True
    require_risk_gate_pass_signed_testnet: bool = True
    require_real_read_only_venue_probe_valid: bool = True
    max_venue_probe_age_sec: int = 600
    require_canonical_id_chain: bool = True
    require_idempotency_key: bool = True
    require_metadata_only_secret: bool = True
    create_would_submit_payload: bool = True
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    testnet_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    signed_order_executor_enabled: bool = False
    ready_for_signed_testnet_execution: bool = False
    live_trading_allowed_by_this_module: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_would_submit_order_payload(order_intent: Mapping[str, Any], *, venue_probe: Mapping[str, Any] | None = None) -> dict[str, Any]:
    intent = dict(order_intent or {})
    probe = dict(venue_probe or {})
    symbol = str(intent.get("symbol") or "BTCUSDT")
    side = str(intent.get("side") or ("BUY" if intent.get("direction") == "LONG" else "SELL" if intent.get("direction") == "SHORT" else "")).upper()
    order_type = str(intent.get("testnet_order_type") or intent.get("order_type") or "MARKET").replace("_PAPER", "").upper()
    quantity = _safe_float(intent.get("quantity") or intent.get("qty"), 0.0)
    price = intent.get("limit_price") or intent.get("price") or intent.get("entry_price")
    time_in_force = str(intent.get("time_in_force") or "GTC")
    payload_base = {
        "order_intent_id": intent.get("order_intent_id"),
        "decision_id": intent.get("decision_id"),
        "risk_gate_id": intent.get("risk_gate_id"),
        "research_signal_id": intent.get("research_signal_id"),
        "profile_id": intent.get("profile_id"),
        "venue": probe.get("venue") or intent.get("venue") or "binance_futures_testnet",
        "environment": "testnet",
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "price": _safe_float(price, 0.0) if price not in {None, ""} else None,
        "time_in_force": time_in_force,
        "reduce_only": bool(intent.get("reduce_only", False)),
        "client_order_id": intent.get("client_order_id") or intent.get("idempotency_key"),
    }
    idempotency_source = {
        "order_intent_id": payload_base.get("order_intent_id"),
        "risk_gate_id": payload_base.get("risk_gate_id"),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "type": order_type,
    }
    idempotency_key = stable_id("step306_signed_testnet_pre_submit_idempotency", idempotency_source, 32)
    payload_base["idempotency_key"] = idempotency_key
    payload_base["client_order_id"] = payload_base.get("client_order_id") or idempotency_key
    payload_base["would_submit_only"] = True
    payload_base["actual_submission_performed"] = False
    payload_base["external_order_submission_performed"] = False
    payload_base["place_order_enabled"] = False
    payload_base["signed_order_executor_enabled"] = False
    payload_base["created_at_utc"] = utc_now_canonical()
    payload_base["would_submit_order_payload_sha256"] = sha256_json(_drop_hashes(payload_base, "would_submit_order_payload_sha256"))
    return payload_base


def build_signed_testnet_pre_submit_validation_report(
    *,
    order_intent: Mapping[str, Any] | None,
    risk_gate_report: Mapping[str, Any] | None,
    venue_probe: Mapping[str, Any] | None,
    max_venue_probe_age_sec: int = 600,
) -> dict[str, Any]:
    intent = dict(order_intent or {})
    risk = dict(risk_gate_report or intent.get("risk_gate_report") or {})
    probe = dict(venue_probe or {})
    policy = SignedTestnetPreSubmitPolicy(max_venue_probe_age_sec=max_venue_probe_age_sec)
    blockers: list[str] = []
    warnings: list[str] = []

    if not intent:
        blockers.append(BLOCK_MISSING_ORDER_INTENT)
    if intent and intent.get("order_intent_created") is not True and intent.get("status") != "ORDER_INTENT_CREATED":
        blockers.append(BLOCK_ORDER_INTENT_NOT_CREATED)

    stage = str(intent.get("execution_stage") or intent.get("decision_stage") or "").lower()
    if intent and stage not in {"signed_testnet", "testnet"}:
        blockers.append(BLOCK_ORDER_INTENT_STAGE_NOT_SIGNED_TESTNET)

    missing_chain = [field for field in _REQUIRED_ORDER_FIELDS if not intent.get(field)]
    if missing_chain:
        blockers.append(BLOCK_MISSING_CANONICAL_ID_CHAIN)

    if not risk:
        blockers.append(BLOCK_MISSING_RISK_GATE)
    risk_status = str(risk.get("status") or intent.get("risk_gate_status") or "")
    if risk and risk_status != "PASS_SIGNED_TESTNET":
        blockers.append(BLOCK_RISK_GATE_NOT_SIGNED_TESTNET)
    if risk and risk.get("approved") is not True:
        blockers.append(BLOCK_RISK_GATE_NOT_APPROVED)
    if risk and intent.get("risk_gate_id") and risk.get("risk_gate_id") and intent.get("risk_gate_id") != risk.get("risk_gate_id"):
        blockers.append(BLOCK_MISSING_CANONICAL_ID_CHAIN)

    if not probe:
        blockers.append(BLOCK_MISSING_VENUE_PROBE)
    if probe and probe.get("valid") is not True:
        blockers.append(BLOCK_VENUE_PROBE_INVALID)
    if probe and probe.get("status") != "REAL_READ_ONLY_VENUE_PROBE_VALID":
        blockers.append(BLOCK_VENUE_PROBE_INVALID)
    probe_age = _canonical_age_sec(probe.get("created_at_utc")) if probe else None
    if probe and (probe_age is None or probe_age > max_venue_probe_age_sec):
        blockers.append(BLOCK_VENUE_PROBE_STALE)
    if probe and probe.get("environment") != "testnet":
        blockers.append(BLOCK_VENUE_PROBE_INVALID)
    if probe and probe.get("metadata_only") is not True:
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    unsafe_flags = {
        "testnet_order_submission_allowed": any(
            _safe_bool(src.get("testnet_order_submission_allowed")) for src in [intent, risk, probe]
        ),
        "external_order_submission_allowed": any(
            _safe_bool(src.get("external_order_submission_allowed")) for src in [intent, risk, probe]
        ),
        "external_order_submission_performed": any(
            _safe_bool(src.get("external_order_submission_performed")) for src in [intent, risk, probe]
        ),
        "place_order_enabled": any(_safe_bool(src.get("place_order_enabled")) for src in [intent, risk, probe]),
        "cancel_order_enabled": any(_safe_bool(src.get("cancel_order_enabled")) for src in [intent, risk, probe]),
        "signed_order_executor_enabled": any(_safe_bool(src.get("signed_order_executor_enabled")) for src in [intent, risk, probe]),
        "live_trading_allowed_by_this_module": any(
            _safe_bool(src.get("live_trading_allowed_by_this_module")) for src in [intent, risk, probe]
        ),
        "api_key_value_access_allowed": probe.get("api_key_value_access_allowed") is not False if probe else False,
        "api_secret_value_access_allowed": probe.get("api_secret_value_access_allowed") is not False if probe else False,
        "secret_file_access_allowed": probe.get("secret_file_access_allowed") is not False if probe else False,
        "secret_file_creation_allowed": probe.get("secret_file_creation_allowed") is not False if probe else False,
    }
    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_SUBMISSION_FLAG)
    if any(unsafe_flags.get(name) for name in [
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
    ]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    payload_eligible = bool(intent) and intent.get("order_intent_created") is True and intent.get("status") == "ORDER_INTENT_CREATED" and stage in {"signed_testnet", "testnet"} and not missing_chain
    would_submit_payload = build_would_submit_order_payload(intent, venue_probe=probe) if payload_eligible else None
    valid = not blockers
    payload_base = {
        "version": STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION,
        "order_intent_id": intent.get("order_intent_id"),
        "risk_gate_id": intent.get("risk_gate_id") or risk.get("risk_gate_id"),
        "venue_probe_id": probe.get("real_read_only_venue_probe_id"),
        "would_submit_order_payload_sha256": (would_submit_payload or {}).get("would_submit_order_payload_sha256"),
        "block_reasons": sorted(set(blockers)),
    }
    report = {
        "signed_testnet_pre_submit_validation_id": stable_id("step306_signed_testnet_pre_submit_validation", payload_base, 24),
        "version": STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION,
        "status": PRE_SUBMIT_VALIDATED_REVIEW_ONLY if valid else PRE_SUBMIT_BLOCKED,
        "valid": valid,
        "review_only": True,
        "ready_for_execution_enablement_packet": valid,
        "would_submit_order_payload_created": would_submit_payload is not None,
        "would_submit_order_payload": would_submit_payload,
        "idempotency_key": (would_submit_payload or {}).get("idempotency_key"),
        "order_intent_id": intent.get("order_intent_id"),
        "decision_id": intent.get("decision_id"),
        "risk_gate_id": intent.get("risk_gate_id") or risk.get("risk_gate_id"),
        "research_signal_id": intent.get("research_signal_id"),
        "profile_id": intent.get("profile_id"),
        "risk_gate_status": risk_status or None,
        "risk_gate_approved": risk.get("approved") is True,
        "venue_probe_id": probe.get("real_read_only_venue_probe_id"),
        "venue_probe_status": probe.get("status"),
        "venue_probe_valid": probe.get("valid") is True,
        "venue_probe_source_age_sec": probe_age,
        "missing_canonical_id_fields": missing_chain,
        "unsafe_flag_evidence": unsafe_flags,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "policy": policy.to_dict(),
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "actual_submission_performed": False,
        "adapter_called_for_write": False,
        "created_at_utc": utc_now_canonical(),
    }
    report["signed_testnet_pre_submit_validation_sha256"] = sha256_json(
        _drop_hashes(report, "signed_testnet_pre_submit_validation_sha256")
    )
    return report


def build_signed_testnet_pre_submit_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    record = {
        "version": STEP306_SIGNED_TESTNET_PRE_SUBMIT_VALIDATOR_VERSION,
        "signed_testnet_pre_submit_validation_id": data.get("signed_testnet_pre_submit_validation_id"),
        "signed_testnet_pre_submit_validation_sha256": data.get("signed_testnet_pre_submit_validation_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "review_only": True,
        "ready_for_execution_enablement_packet": data.get("ready_for_execution_enablement_packet") is True,
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "venue_probe_id": data.get("venue_probe_id"),
        "would_submit_order_payload_sha256": (data.get("would_submit_order_payload") or {}).get("would_submit_order_payload_sha256"),
        "idempotency_key": data.get("idempotency_key"),
        "block_reasons": list(data.get("block_reasons") or []),
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_pre_submit_registry_record_id"] = stable_id("step306_signed_testnet_pre_submit_registry", record, 24)
    record["signed_testnet_pre_submit_registry_record_sha256"] = sha256_json(record)
    return record


def persist_signed_testnet_pre_submit_validation_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    pre_submit_dir = cfg.root / "storage" / "signed_testnet_pre_submit"
    pre_submit_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    record = build_signed_testnet_pre_submit_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, SIGNED_TESTNET_PRE_SUBMIT_REGISTRY_NAME),
        record,
        registry_name=SIGNED_TESTNET_PRE_SUBMIT_REGISTRY_NAME,
        id_field="signed_testnet_pre_submit_registry_record_id",
        hash_field="signed_testnet_pre_submit_registry_record_sha256",
        id_prefix="step306_signed_testnet_pre_submit_registry",
    )
    payload["signed_testnet_pre_submit_registry_record_id"] = persisted.get("signed_testnet_pre_submit_registry_record_id")
    payload["signed_testnet_pre_submit_registry_record_sha256"] = persisted.get("signed_testnet_pre_submit_registry_record_sha256")
    if payload.get("would_submit_order_payload"):
        atomic_write_json(pre_submit_dir / "would_submit_order_payload.json", payload["would_submit_order_payload"])
        atomic_write_json(latest_dir / "would_submit_order_payload.json", payload["would_submit_order_payload"])
    else:
        blocked_payload = {
            "status": "WOULD_SUBMIT_ORDER_PAYLOAD_NOT_CREATED",
            "reason": "STEP306_PRE_SUBMIT_VALIDATION_BLOCKED_BEFORE_PAYLOAD_CREATION",
            "signed_testnet_pre_submit_validation_id": payload.get("signed_testnet_pre_submit_validation_id"),
            "block_reasons": list(payload.get("block_reasons") or []),
            "actual_submission_performed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "signed_order_executor_enabled": False,
            "created_at_utc": utc_now_canonical(),
        }
        atomic_write_json(pre_submit_dir / "would_submit_order_payload.json", blocked_payload)
        atomic_write_json(latest_dir / "would_submit_order_payload.json", blocked_payload)
    atomic_write_json(pre_submit_dir / "pre_submit_validation_report.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_pre_submit_validation_report.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_pre_submit_registry_record.json", persisted)
    return payload


def _read_latest_json(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def run_signed_testnet_pre_submit_validator_latest(
    *,
    project_root: str | Path | None = None,
    order_intent: Mapping[str, Any] | None = None,
    risk_gate_report: Mapping[str, Any] | None = None,
    venue_probe: Mapping[str, Any] | None = None,
    max_venue_probe_age_sec: int = 600,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    order_intent_path = cfg.root / ORDER_INTENT_PATH
    order_result_path = cfg.root / ORDER_RESULT_PATH
    trade_decision_path = cfg.root / TRADE_DECISION_PATH
    intent = dict(order_intent or _read_latest_json(order_intent_path))
    order_result = _read_latest_json(order_result_path)
    if not intent and isinstance(order_result.get("intent"), Mapping):
        intent = dict(order_result.get("intent") or {})
    trade_decision = _read_latest_json(trade_decision_path)
    if not intent and isinstance(trade_decision, Mapping):
        intent = dict(trade_decision.get("order_intent") or {})
    risk = dict(risk_gate_report or intent.get("risk_gate_report") or trade_decision.get("pre_order_risk_gate") or trade_decision.get("risk_gate_report") or {})
    probe = dict(venue_probe or _read_latest_json(latest_dir / "real_read_only_venue_probe.json"))
    if not probe:
        probe = run_real_read_only_venue_probe_latest(project_root=cfg.root)
    report = build_signed_testnet_pre_submit_validation_report(
        order_intent=intent,
        risk_gate_report=risk,
        venue_probe=probe,
        max_venue_probe_age_sec=max_venue_probe_age_sec,
    )
    return persist_signed_testnet_pre_submit_validation_report(cfg, report)
