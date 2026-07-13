from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

APPROVAL_REVIEW_VERSION = "lean_approval_review_v1"

STATUS_WAITING_FOR_MANUAL_SUBMISSION = (
    "APPROVAL_REVIEW_WAITING_FOR_MANUAL_SUBMISSION_REVIEW_ONLY"
)
STATUS_SUBMISSION_RECORDED_REVIEW_ONLY = (
    "APPROVAL_REVIEW_SUBMISSION_RECORDED_NOT_RUNTIME_AUTHORITY"
)
STATUS_BLOCKED_REVIEW_ONLY = "APPROVAL_REVIEW_BLOCKED_REVIEW_ONLY"

STATE_WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
STATE_SUBMITTED_REVIEW_ONLY = "SUBMITTED_REVIEW_ONLY"
STATE_BLOCKED = "BLOCKED"

# A missing manual submission is the expected pre-approval state. It is not a
# runtime error and never grants permission.
_EXPECTED_WAITING_BLOCKERS = {
    "MANUAL_APPROVAL_SUBMISSION_MISSING",
}

_UNSAFE_FLAGS = (
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "approval_packet_created",
    "approval_intake_validated",
    "signed_testnet_unlock_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_trading_allowed",
    "live_trading_allowed_by_this_module",
    "external_order_submission_performed",
    "auto_promotion_allowed",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig) -> Path:
    path = cfg.root / "storage" / "governance" / "approval"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _block_reasons(payload: Mapping[str, Any]) -> list[str]:
    for field in ("block_reasons", "blockers", "readiness_blockers"):
        value = payload.get(field)
        if isinstance(value, list):
            return sorted({str(item) for item in value})
    return []


def _component(
    *,
    name: str,
    payload: Mapping[str, Any] | None,
    id_field: str,
    hash_field: str,
) -> dict[str, Any]:
    source = dict(payload or {})
    return {
        "component": name,
        "source_id": source.get(id_field),
        "source_sha256": source.get(hash_field),
        "status": source.get("status"),
        "blocked": source.get("blocked") is True,
        "fail_closed": source.get("fail_closed") is True,
        "review_only": source.get("review_only") is True,
        "block_reasons": _block_reasons(source),
        "unsafe_true_flags": sorted(
            field for field in _UNSAFE_FLAGS if _bool(source.get(field))
        ),
    }


def _intake_is_expected_waiting(
    intake: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> bool:
    if intake.get("manual_approval_submission_present") is True:
        return False
    reasons = set(projection.get("block_reasons") or [])
    return bool(reasons) and reasons.issubset(_EXPECTED_WAITING_BLOCKERS)


def build_approval_review_report(
    *,
    intake_validation: Mapping[str, Any],
    operator_handoff: Mapping[str, Any],
    fixture_validation: Mapping[str, Any],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()

    components = {
        "intake_validation": _component(
            name="intake_validation",
            payload=intake_validation,
            id_field="phase5_manual_approval_intake_validation_id",
            hash_field="phase5_report_sha256",
        ),
        "operator_handoff": _component(
            name="operator_handoff",
            payload=operator_handoff,
            id_field="phase5_1_manual_approval_operator_handoff_id",
            hash_field="phase5_1_report_sha256",
        ),
        "fixture_validation": _component(
            name="fixture_validation",
            payload=fixture_validation,
            id_field="phase5_2_manual_approval_submission_fixture_validator_id",
            hash_field="phase5_2_report_sha256",
        ),
    }

    blockers: list[str] = []
    intake_waiting = _intake_is_expected_waiting(
        intake_validation,
        components["intake_validation"],
    )

    for name, projection in components.items():
        if not projection["source_id"]:
            blockers.append(f"APPROVAL_COMPONENT_ID_MISSING:{name}")
        if not projection["status"]:
            blockers.append(f"APPROVAL_COMPONENT_STATUS_MISSING:{name}")
        if projection["unsafe_true_flags"]:
            blockers.append(f"APPROVAL_COMPONENT_UNSAFE_FLAG:{name}")

        if projection["blocked"] or projection["fail_closed"]:
            if name == "intake_validation" and intake_waiting:
                continue
            blockers.append(f"APPROVAL_COMPONENT_BLOCKED:{name}")

    manual_submission_present = (
        intake_validation.get("manual_approval_submission_present") is True
    )
    fixture_contract_ready = (
        fixture_validation.get(
            "valid_fixture_passed_review_only_validation"
        ) is True
        and fixture_validation.get(
            "invalid_fixtures_blocked_fail_closed"
        ) is True
    )
    handoff_ready = (
        operator_handoff.get(
            "manual_approval_submission_template_created"
        ) is True
        and operator_handoff.get(
            "manual_approval_submission_created"
        ) is False
    )

    if not manual_submission_present:
        if not handoff_ready:
            blockers.append("APPROVAL_OPERATOR_HANDOFF_NOT_READY")
        if not fixture_contract_ready:
            blockers.append("APPROVAL_FIXTURE_CONTRACT_NOT_READY")

    blockers = sorted(set(blockers))
    blocked = bool(blockers)

    if blocked:
        state = STATE_BLOCKED
        status = STATUS_BLOCKED_REVIEW_ONLY
        next_action = "resolve_approval_review_blockers"
    elif manual_submission_present:
        state = STATE_SUBMITTED_REVIEW_ONLY
        status = STATUS_SUBMISSION_RECORDED_REVIEW_ONLY
        next_action = "manual_governance_review_required_no_runtime_unlock"
    else:
        state = STATE_WAITING_FOR_HUMAN
        status = STATUS_WAITING_FOR_MANUAL_SUBMISSION
        next_action = "human_review_then_manual_submission"

    seed = {
        "version": APPROVAL_REVIEW_VERSION,
        "state": state,
        "component_ids": {
            name: projection.get("source_id")
            for name, projection in components.items()
        },
        "created_at_utc": created,
    }

    report: dict[str, Any] = {
        "approval_review_id": stable_id("approval_review", seed, 24),
        "approval_review_version": APPROVAL_REVIEW_VERSION,
        "status": status,
        "approval_state": state,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "paper_only": True,
        "manual_approval_required": True,
        "manual_approval_submission_present": manual_submission_present,
        "intake_waiting_state_expected": intake_waiting,
        "operator_handoff_ready": handoff_ready,
        "fixture_contract_ready": fixture_contract_ready,
        "components": components,
        "blockers": blockers,
        "next_action": next_action,
        "runtime_permission_source": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "auto_promotion_allowed": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "created_at_utc": created,
    }
    report["approval_review_sha256"] = sha256_json(report)
    return report


def run_approval_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    intake_runner: Callable[..., Mapping[str, Any]] | None = None,
    handoff_runner: Callable[..., Mapping[str, Any]] | None = None,
    fixture_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the historical Phase 5 chain behind one semantic approval entry point."""

    cfg = cfg or load_config(project_root)

    if intake_runner is None:
        from crypto_ai_system.governance.approval_intake import (
            persist_phase5_manual_approval_intake_validation_report,
        )
        intake_runner = persist_phase5_manual_approval_intake_validation_report

    if handoff_runner is None:
        from crypto_ai_system.governance.operator_handoff import (
            persist_phase5_1_manual_approval_operator_handoff_report,
        )
        handoff_runner = persist_phase5_1_manual_approval_operator_handoff_report

    if fixture_runner is None:
        from crypto_ai_system.governance.approval_fixtures import (
            persist_phase5_2_manual_approval_submission_fixture_validator_report,
        )
        fixture_runner = (
            persist_phase5_2_manual_approval_submission_fixture_validator_report
        )

    intake = dict(intake_runner(cfg=cfg))
    handoff = dict(handoff_runner(cfg=cfg))
    fixtures = dict(fixture_runner(cfg=cfg))

    report = build_approval_review_report(
        intake_validation=intake,
        operator_handoff=handoff,
        fixture_validation=fixtures,
    )

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg)
    atomic_write_json(latest / "approval_review_report.json", report)
    atomic_write_json(storage / "approval_review_report.json", report)

    return {
        "report": report,
        "legacy_outputs": {
            "intake_validation": intake,
            "operator_handoff": handoff,
            "fixture_validation": fixtures,
        },
    }


def run_approval_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return run_approval_review_chain(
        cfg=cfg,
        project_root=project_root,
    )["report"]


__all__ = [
    "APPROVAL_REVIEW_VERSION",
    "STATE_WAITING_FOR_HUMAN",
    "STATE_SUBMITTED_REVIEW_ONLY",
    "STATE_BLOCKED",
    "STATUS_WAITING_FOR_MANUAL_SUBMISSION",
    "STATUS_SUBMISSION_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_approval_review_report",
    "run_approval_review_chain",
    "run_approval_review_latest",
]
