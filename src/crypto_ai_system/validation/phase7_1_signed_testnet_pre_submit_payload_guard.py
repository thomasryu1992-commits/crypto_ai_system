from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE7_1_VERSION = "phase7_1_signed_testnet_pre_submit_payload_guard_v1"
PHASE7_1_REGISTRY_NAME = "phase7_1_signed_testnet_pre_submit_payload_guard_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_BLOCKED_REVIEW_ONLY"

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_SOURCE_ARTIFACTS = {
    "phase6_6_actual_intake_validation_bridge": "phase6_6_actual_intake_validation_bridge_report.json",
    "phase7_signed_testnet_validation_design_guard": "phase7_signed_testnet_validation_design_guard_report.json",
    "signed_testnet_validation_design_packet": "signed_testnet_validation_design_packet_review_only.json",
    "signed_testnet_disabled_executor_guard": "signed_testnet_disabled_executor_guard_report.json",
}

REQUIRED_PAYLOAD_FIELDS = [
    "symbol",
    "side",
    "order_type",
    "quantity",
    "notional",
    "time_in_force",
    "idempotency_key",
    "canonical_id_chain",
]

REQUIRED_ID_CHAIN_FIELDS = [
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
]


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = _unsafe_fields(payload)
        if flags:
            unsafe[name] = flags
    return unsafe


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase6_6_report_sha256",
        "phase7_report_sha256",
        "signed_testnet_validation_design_packet_sha256",
        "disabled_executor_guard_report_sha256",
        "phase7_1_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _positive_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _read_optional_json(path: Path) -> dict[str, Any]:
    payload = read_json(path, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _build_canonical_id_chain(cfg: AppConfig) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    phase5 = _read_optional_json(latest / "phase5_manual_approval_intake_validation_report.json")
    phase3 = _read_optional_json(latest / "paper_strategy_validation_report.json")
    paper_decision = _read_optional_json(latest / "paper_trade_decision.json")
    risk_gate = _read_optional_json(latest / "pre_order_risk_gate_report.json")
    order_intent = _read_optional_json(latest / "paper_order_intent.json")
    signal = _read_optional_json(latest / "research_signal.json")
    return {
        "data_snapshot_id": phase5.get("data_snapshot_id") or phase3.get("data_snapshot_id"),
        "feature_snapshot_id": phase5.get("feature_snapshot_id") or phase3.get("feature_snapshot_id"),
        "research_signal_id": signal.get("research_signal_id") or phase3.get("research_signal_id") or "research_signal_review_only_fixture",
        "profile_id": phase5.get("candidate_profile_id") or signal.get("profile_id") or "profile_review_only_fixture",
        "approval_packet_id": phase5.get("approval_packet_draft_id") or "approval_packet_review_only_fixture",
        "approval_intake_id": phase5.get("approval_intake_validation_record_id") or "approval_intake_review_only_fixture",
        "decision_id": paper_decision.get("decision_id") or phase3.get("decision_id") or "decision_review_only_fixture",
        "risk_gate_id": risk_gate.get("risk_gate_id") or phase3.get("risk_gate_id") or "risk_gate_review_only_fixture",
        "order_intent_id": order_intent.get("order_intent_id") or phase3.get("order_intent_id") or "order_intent_review_only_fixture",
    }


def _build_valid_payload_fixture(cfg: AppConfig, *, phase7_report: Mapping[str, Any]) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    operator = _read_optional_json(latest / "operator_unlock_request.json")
    max_notional = float(operator.get("max_testnet_notional_usd") or 25.0)
    notional = min(max_notional, 25.0)
    chain = _build_canonical_id_chain(cfg)
    return {
        "fixture_type": "signed_testnet_would_submit_payload_fixture_review_only",
        "fixture_version": PHASE7_1_VERSION,
        "review_only": True,
        "would_submit_only": True,
        "do_not_submit_order": True,
        "source_phase7_design_guard_id": phase7_report.get("phase7_signed_testnet_validation_design_guard_id"),
        "symbol": str(operator.get("allowed_symbol") or "BTCUSDT"),
        "side": "SELL",
        "order_type": "MARKET",
        "quantity": 0.001,
        "notional": notional,
        "time_in_force": "GTC",
        "idempotency_key": stable_id("signed_testnet_would_submit_payload", {"chain": chain, "notional": notional}, 24),
        "canonical_id_chain": chain,
        "max_testnet_notional_usd": max_notional,
        "kill_switch_rechecked": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "reconciliation_required_after_any_testnet_session": True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }


def _validate_would_submit_payload(payload: Mapping[str, Any], *, max_notional: float | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    blockers: list[str] = []
    missing = [field for field in REQUIRED_PAYLOAD_FIELDS if data.get(field) in (None, "", [])]
    if missing:
        blockers.append("MISSING_REQUIRED_PAYLOAD_FIELDS:" + ",".join(missing))

    chain = data.get("canonical_id_chain") if isinstance(data.get("canonical_id_chain"), Mapping) else {}
    missing_chain = [field for field in REQUIRED_ID_CHAIN_FIELDS if not chain.get(field)]
    if missing_chain:
        blockers.append("MISSING_CANONICAL_ID_CHAIN_FIELDS:" + ",".join(missing_chain))

    if not _positive_number(data.get("quantity")):
        blockers.append("QUANTITY_NOT_POSITIVE_NUMERIC")
    if not _positive_number(data.get("notional")):
        blockers.append("NOTIONAL_NOT_POSITIVE_NUMERIC")
    if max_notional is not None:
        try:
            if float(data.get("notional")) > max_notional:
                blockers.append("HARD_CAP_EXCEEDED_MAX_TESTNET_NOTIONAL")
        except (TypeError, ValueError):
            blockers.append("NOTIONAL_NOT_NUMERIC_FOR_HARD_CAP_CHECK")

    for field in ("kill_switch_rechecked", "hard_caps_rechecked", "pre_order_risk_gate_rechecked"):
        if data.get(field) is not True:
            blockers.append(f"{field.upper()}_NOT_TRUE")

    unsafe = _unsafe_fields(data)
    if unsafe:
        blockers.append("UNSAFE_WOULD_SUBMIT_PAYLOAD_FLAG:" + ",".join(unsafe))

    return {
        "payload_valid_review_only": not blockers,
        "payload_blocked_fail_closed": bool(blockers),
        "missing_required_payload_fields": missing,
        "missing_canonical_id_chain_fields": missing_chain,
        "unsafe_truthy_fields": unsafe,
        "payload_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_disabled_executor_fixture_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "guard_type": "signed_testnet_disabled_executor_fixture_guard_review_only",
        "source_phase7_1_guard_id": report.get("phase7_1_signed_testnet_pre_submit_payload_guard_id"),
        "guard_passed": True,
        "disabled_executor_attempt_result": "SIGNED_TESTNET_ORDER_SUBMISSION_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY",
        "would_submit_payload_valid_review_only": report.get("valid_would_submit_payload_passed_review_only_validation"),
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
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
        "created_at_utc": report.get("created_at_utc"),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return f"""# Phase 7.1 Signed Testnet Disabled Executor Fixture & Pre-submit Payload Guard — Review Only

Status: `{report.get('status')}`

This phase creates would-submit payload fixtures and validates that the signed testnet executor remains disabled. It does not submit testnet orders and does not enable execution.

## Result

- Phase 7.1 payload guard ready review-only: `{report.get('phase7_1_payload_guard_ready_review_only')}`
- Valid would-submit payload fixture passed: `{report.get('valid_would_submit_payload_passed_review_only_validation')}`
- Invalid payload fixtures blocked: `{report.get('invalid_payload_fixtures_blocked_fail_closed')}`
- Disabled executor guard passed: `{report.get('disabled_executor_guard_passed')}`
- External order submission performed: `{report.get('external_order_submission_performed')}`

## Blockers

{blocker_lines}

## Disabled Executor Invariants

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
"""


def build_phase7_1_signed_testnet_pre_submit_payload_guard_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    created = utc_now_canonical()
    artifacts = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing_artifacts = [name for name, payload in artifacts.items() if not payload]
    unsafe_flags = _unsafe_flags_by_artifact(artifacts)
    phase7 = artifacts.get("phase7_signed_testnet_validation_design_guard", {})
    design_packet = artifacts.get("signed_testnet_validation_design_packet", {})
    disabled_guard = artifacts.get("signed_testnet_disabled_executor_guard", {})
    operator = _read_optional_json(latest / "operator_unlock_request.json")
    max_notional = None
    if operator.get("max_testnet_notional_usd") is not None:
        try:
            max_notional = float(operator.get("max_testnet_notional_usd"))
        except (TypeError, ValueError):
            max_notional = None

    valid_payload = _build_valid_payload_fixture(cfg, phase7_report=phase7)
    invalid_payloads = {
        "invalid_missing_idempotency_key": {**valid_payload, "idempotency_key": ""},
        "invalid_hard_cap_exceeded": {**valid_payload, "notional": (max_notional or 25.0) + 1000.0},
        "invalid_missing_id_chain": {**valid_payload, "canonical_id_chain": {}},
        "invalid_unsafe_order_submission_flag": {**valid_payload, "testnet_order_submission_allowed": True, "place_order_enabled": True},
    }
    valid_result = _validate_would_submit_payload(valid_payload, max_notional=max_notional)
    invalid_results = {name: _validate_would_submit_payload(payload, max_notional=max_notional) for name, payload in invalid_payloads.items()}

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_1_SOURCE_ARTIFACT:{name}" for name in missing_artifacts])
    if unsafe_flags:
        blockers.extend([f"UNSAFE_PHASE7_1_SOURCE_FLAG:{name}:{','.join(flags)}" for name, flags in unsafe_flags.items()])

    phase7_ready = phase7.get("status") == "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_RECORDED_REVIEW_ONLY" and phase7.get("phase7_design_ready_review_only") is True
    if not phase7_ready:
        blockers.append("PHASE7_DESIGN_GUARD_NOT_READY")
    design_ready = design_packet.get("phase7_design_ready_review_only") is True and design_packet.get("signed_testnet_order_submission_authority") is False
    if not design_ready:
        blockers.append("SIGNED_TESTNET_VALIDATION_DESIGN_PACKET_NOT_READY_OR_NOT_REVIEW_ONLY")
    executor_disabled = (
        disabled_guard.get("guard_passed") is True
        and disabled_guard.get("testnet_order_submission_allowed") is False
        and disabled_guard.get("signed_order_executor_enabled") is False
        and disabled_guard.get("external_order_submission_performed") is False
    )
    if not executor_disabled:
        blockers.append("DISABLED_EXECUTOR_GUARD_NOT_PASSED")
    if not valid_result.get("payload_valid_review_only"):
        blockers.extend(valid_result.get("payload_blockers") or ["VALID_WOULD_SUBMIT_PAYLOAD_DID_NOT_VALIDATE"])
    invalid_all_blocked = all(result.get("payload_blocked_fail_closed") is True for result in invalid_results.values())
    if not invalid_all_blocked:
        blockers.append("ONE_OR_MORE_INVALID_WOULD_SUBMIT_PAYLOAD_FIXTURES_DID_NOT_BLOCK")

    for artifact_name, payload in artifacts.items():
        if payload.get("ready_for_signed_testnet_execution") is True:
            blockers.append(f"UNSAFE_READY_FOR_SIGNED_TESTNET_TRUE:{artifact_name}")
        if payload.get("testnet_order_submission_allowed") is True:
            blockers.append(f"UNSAFE_TESTNET_ORDER_SUBMISSION_ALLOWED_TRUE:{artifact_name}")
        if payload.get("external_order_submission_performed") is True:
            blockers.append(f"UNSAFE_EXTERNAL_ORDER_SUBMISSION_PERFORMED_TRUE:{artifact_name}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    phase7_1_id = stable_id(
        "phase7_1_signed_testnet_pre_submit_payload_guard",
        {
            "source_hashes": {name: _artifact_hash(payload) for name, payload in artifacts.items()},
            "valid_payload_hash": sha256_json(valid_payload),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase7_1_signed_testnet_pre_submit_payload_guard_id": phase7_1_id,
        "phase7_1_version": PHASE7_1_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "payload_fixture_only": True,
        "disabled_executor_guard": True,
        "phase7_1_payload_guard_ready_review_only": ready,
        "would_submit_payload_fixture_created": True,
        "valid_would_submit_payload_passed_review_only_validation": valid_result.get("payload_valid_review_only") is True,
        "invalid_payload_fixture_count": len(invalid_payloads),
        "invalid_payload_fixtures_blocked_fail_closed": invalid_all_blocked,
        "valid_payload_validation": valid_result,
        "invalid_payload_validation": invalid_results,
        "disabled_executor_guard_passed": executor_disabled,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "actual_order_submission_performed": False,
        "signed_testnet_validation_fixture_only": True,
        "missing_source_artifacts": missing_artifacts,
        "unsafe_flags_by_artifact": unsafe_flags,
        "source_evidence_hash_summary": {name: _source_summary(name, payload) for name, payload in artifacts.items()},
        "block_reasons": blockers,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "recommended_next_action": "prepare_future_phase7_2_signed_testnet_executor_enablement_review_but_keep_executor_disabled" if ready else "resolve_phase7_1_payload_guard_blockers_and_rerun_phase7_1",
        "created_at_utc": created,
    }
    report["valid_would_submit_payload_fixture_sha256"] = sha256_json(valid_payload)
    report["disabled_executor_fixture_guard_report_sha256"] = sha256_json(_build_disabled_executor_fixture_report(report))
    report["phase7_1_report_sha256"] = sha256_json(report)
    return report


def persist_phase7_1_signed_testnet_pre_submit_payload_guard_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_1_signed_testnet_pre_submit_payload_guard")
    fixtures_dir = _storage_dir(cfg, "storage/signed_testnet/fixtures")
    report = build_phase7_1_signed_testnet_pre_submit_payload_guard_report(cfg=cfg)
    phase7 = _read_latest_json(cfg, "phase7_signed_testnet_validation_design_guard_report.json")
    valid_payload = _build_valid_payload_fixture(cfg, phase7_report=phase7)
    operator = _read_optional_json(latest / "operator_unlock_request.json")
    max_notional = float(operator.get("max_testnet_notional_usd") or 25.0)
    invalid_payloads = {
        "invalid_missing_idempotency_key": {**valid_payload, "idempotency_key": ""},
        "invalid_hard_cap_exceeded": {**valid_payload, "notional": max_notional + 1000.0},
        "invalid_missing_id_chain": {**valid_payload, "canonical_id_chain": {}},
        "invalid_unsafe_order_submission_flag": {**valid_payload, "testnet_order_submission_allowed": True, "place_order_enabled": True},
    }
    disabled_executor_report = _build_disabled_executor_fixture_report(report)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_1_signed_testnet_pre_submit_payload_guard_report.json", report)
    atomic_write_json(latest / "signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json", valid_payload)
    atomic_write_json(latest / "signed_testnet_disabled_executor_fixture_guard_report.json", disabled_executor_report)
    (latest / "SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(phase_dir / "phase7_1_signed_testnet_pre_submit_payload_guard_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json", valid_payload)
    atomic_write_json(phase_dir / "signed_testnet_disabled_executor_fixture_guard_report.json", disabled_executor_report)
    (phase_dir / "SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(fixtures_dir / "valid_would_submit_payload_FIXTURE_REVIEW_ONLY.json", valid_payload)
    for name, payload in invalid_payloads.items():
        atomic_write_json(fixtures_dir / f"{name}_would_submit_payload_FIXTURE_REVIEW_ONLY.json", payload)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_1_REGISTRY_NAME),
        {
            "phase7_1_signed_testnet_pre_submit_payload_guard_id": report.get("phase7_1_signed_testnet_pre_submit_payload_guard_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_1_payload_guard_ready_review_only": report.get("phase7_1_payload_guard_ready_review_only"),
            "valid_would_submit_payload_passed_review_only_validation": report.get("valid_would_submit_payload_passed_review_only_validation"),
            "invalid_payload_fixtures_blocked_fail_closed": report.get("invalid_payload_fixtures_blocked_fail_closed"),
            "phase7_execution_authority": False,
            "phase7_order_submission_authority": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "external_order_submission_performed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE7_1_REGISTRY_NAME,
        id_field="phase7_1_signed_testnet_pre_submit_payload_guard_registry_record_id",
        hash_field="phase7_1_signed_testnet_pre_submit_payload_guard_registry_record_sha256",
        id_prefix="phase7_1_signed_testnet_pre_submit_payload_guard_registry_record",
    )
    atomic_write_json(latest / "phase7_1_signed_testnet_pre_submit_payload_guard_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_1_signed_testnet_pre_submit_payload_guard_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_1_signed_testnet_pre_submit_payload_guard_report",
    "persist_phase7_1_signed_testnet_pre_submit_payload_guard_report",
]
