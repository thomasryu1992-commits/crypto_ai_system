from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    bool_value as _bool,
    latest_dir as _latest_dir,
    readiness_review_storage_dir as _storage_dir,
)
from crypto_ai_system.utils.audit import (
    sha256_json,
    stable_id,
    utc_now_canonical,
)

READINESS_REVIEW_VERSION = "lean_readiness_review_v1"

STATE_WAITING_FOR_MANUAL_ARTIFACTS = (
    "WAITING_FOR_MANUAL_ARTIFACTS"
)
STATE_ACTUAL_INTAKE_REVIEW_ONLY = (
    "ACTUAL_INTAKE_REVIEW_ONLY"
)
STATE_BLOCKED = "BLOCKED"

STATUS_WAITING_REVIEW_ONLY = (
    "READINESS_REVIEW_WAITING_FOR_MANUAL_ARTIFACTS"
)
STATUS_ACTUAL_INTAKE_RECORDED_REVIEW_ONLY = (
    "READINESS_REVIEW_ACTUAL_INTAKE_RECORDED_NOT_EXECUTION_AUTHORITY"
)
STATUS_BLOCKED_REVIEW_ONLY = (
    "READINESS_REVIEW_BLOCKED_REVIEW_ONLY"
)

_UNSAFE_FLAGS: tuple[str, ...] = (
    "runtime_permission_source",
    "signed_testnet_unlock_authority",
    "phase7_execution_authority",
    "phase7_order_submission_authority",
    "approval_intake_validated",
    "operator_unlock_request_validated",
    "signed_testnet_preparation_ready",
    "signed_testnet_readiness_passed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "auto_promotion_allowed",
)

_COMPONENT_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "preparation_preview",
        "phase6_signed_testnet_preparation_preview_id",
        "phase6_report_sha256",
    ),
    (
        "operator_unlock_template",
        "phase6_1_signed_testnet_operator_unlock_request_template_id",
        "phase6_1_report_sha256",
    ),
    (
        "operator_unlock_fixtures",
        "phase6_2_operator_unlock_request_fixture_validator_id",
        "phase6_2_report_sha256",
    ),
    (
        "readiness_gate",
        "phase6_3_signed_testnet_readiness_gate_review_id",
        "phase6_3_report_sha256",
    ),
    (
        "readiness_packet",
        "phase6_4_signed_testnet_readiness_review_packet_id",
        "phase6_4_review_packet_sha256",
    ),
    (
        "actual_intake_sandbox",
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_id",
        "phase6_5_report_sha256",
    ),
    (
        "actual_intake_bridge",
        "phase6_6_actual_intake_validation_bridge_id",
        "phase6_6_report_sha256",
    ),
)


def _list(payload: Mapping[str, Any], field: str) -> list[str]:
    value = payload.get(field)

    if not isinstance(value, list):
        return []

    return sorted(
        {
            str(item)
            for item in value
        }
    )


def _mapping_has_values(
    payload: Mapping[str, Any],
    field: str,
) -> bool:
    value = payload.get(field)
    return isinstance(value, Mapping) and bool(value)


def _component_projection(
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
        "unsafe_true_flags": sorted(
            field
            for field in _UNSAFE_FLAGS
            if _bool(source.get(field))
        ),
    }


def _structural_blockers(
    *,
    legacy_outputs: Mapping[str, Mapping[str, Any]],
    components: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []

    for name, _, _ in _COMPONENT_SPECS:
        source = legacy_outputs.get(name) or {}
        projection = components.get(name) or {}

        if not source:
            blockers.append(
                f"READINESS_COMPONENT_MISSING:{name}"
            )
            continue

        if not projection.get("source_id"):
            blockers.append(
                f"READINESS_COMPONENT_ID_MISSING:{name}"
            )

        if not projection.get("status"):
            blockers.append(
                f"READINESS_COMPONENT_STATUS_MISSING:{name}"
            )

        if projection.get("unsafe_true_flags"):
            blockers.append(
                f"READINESS_COMPONENT_UNSAFE_FLAG:{name}"
            )

    # Preparation evidence must be recordable without enabling execution.
    preview = legacy_outputs.get("preparation_preview") or {}

    if preview.get("blocked") is True:
        blockers.append(
            "READINESS_PREPARATION_PREVIEW_BLOCKED"
        )

    if (
        preview.get("status")
        != "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_RECORDED_REVIEW_ONLY"
    ):
        blockers.append(
            "READINESS_PREPARATION_PREVIEW_STATUS_INVALID"
        )

    template = (
        legacy_outputs.get("operator_unlock_template")
        or {}
    )

    if template.get("blocked") is True:
        blockers.append(
            "READINESS_OPERATOR_UNLOCK_TEMPLATE_BLOCKED"
        )

    if (
        template.get("operator_unlock_request_template_created")
        is not True
    ):
        blockers.append(
            "READINESS_OPERATOR_UNLOCK_TEMPLATE_MISSING"
        )

    fixtures = (
        legacy_outputs.get("operator_unlock_fixtures")
        or {}
    )

    if fixtures.get("blocked") is True:
        blockers.append(
            "READINESS_OPERATOR_UNLOCK_FIXTURE_CONTRACT_BLOCKED"
        )

    if (
        fixtures.get(
            "valid_fixture_passed_review_only_validation"
        )
        is not True
    ):
        blockers.append(
            "READINESS_VALID_UNLOCK_FIXTURE_NOT_PASSED"
        )

    if (
        fixtures.get(
            "invalid_fixtures_blocked_fail_closed"
        )
        is not True
    ):
        blockers.append(
            "READINESS_INVALID_UNLOCK_FIXTURES_NOT_FAIL_CLOSED"
        )

    # Phase 6.3 is deliberately blocked until real human artifacts exist.
    gate = legacy_outputs.get("readiness_gate") or {}

    if (
        gate.get("status")
        != "PHASE6_3_SIGNED_TESTNET_READINESS_GATE_BLOCKED_REVIEW_ONLY"
    ):
        blockers.append(
            "READINESS_GATE_EXPECTED_BLOCKED_STATUS_MISSING"
        )

    if gate.get("blocked") is not True:
        blockers.append(
            "READINESS_GATE_MUST_REMAIN_BLOCKED"
        )

    if _list(
        gate,
        "missing_readiness_source_artifacts",
    ):
        blockers.append(
            "READINESS_GATE_SOURCE_ARTIFACT_MISSING"
        )

    if _mapping_has_values(
        gate,
        "unsafe_flags_by_artifact",
    ):
        blockers.append(
            "READINESS_GATE_UNSAFE_SOURCE_FLAG"
        )

    # Phase 6.4 must record the blocked state as an operator handoff.
    packet = legacy_outputs.get("readiness_packet") or {}

    if (
        packet.get("status")
        != "PHASE6_4_SIGNED_TESTNET_READINESS_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
    ):
        blockers.append(
            "READINESS_PACKET_STATUS_INVALID"
        )

    if (
        packet.get("operator_decision_handoff_created")
        is not True
    ):
        blockers.append(
            "READINESS_OPERATOR_HANDOFF_NOT_CREATED"
        )

    if _list(
        packet,
        "missing_review_packet_source_artifacts",
    ):
        blockers.append(
            "READINESS_PACKET_SOURCE_ARTIFACT_MISSING"
        )

    if _mapping_has_values(
        packet,
        "unsafe_flags_by_artifact",
    ):
        blockers.append(
            "READINESS_PACKET_UNSAFE_SOURCE_FLAG"
        )

    # Phase 6.5 and 6.6 may remain blocked solely because real manual
    # files do not exist yet. Missing upstream evidence or unsafe flags are
    # structural failures, not expected waiting state.
    sandbox = (
        legacy_outputs.get("actual_intake_sandbox")
        or {}
    )

    if _list(sandbox, "missing_source_artifacts"):
        blockers.append(
            "READINESS_SANDBOX_SOURCE_ARTIFACT_MISSING"
        )

    if _mapping_has_values(
        sandbox,
        "unsafe_flags_by_artifact",
    ):
        blockers.append(
            "READINESS_SANDBOX_UNSAFE_SOURCE_FLAG"
        )

    bridge = (
        legacy_outputs.get("actual_intake_bridge")
        or {}
    )

    if _list(bridge, "missing_source_artifacts"):
        blockers.append(
            "READINESS_BRIDGE_SOURCE_ARTIFACT_MISSING"
        )

    if _mapping_has_values(
        bridge,
        "unsafe_flags_by_artifact",
    ):
        blockers.append(
            "READINESS_BRIDGE_UNSAFE_SOURCE_FLAG"
        )

    return sorted(set(blockers))


def build_readiness_review_report(
    *,
    legacy_outputs: Mapping[str, Mapping[str, Any]],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()

    components = {
        name: _component_projection(
            name=name,
            payload=legacy_outputs.get(name),
            id_field=id_field,
            hash_field=hash_field,
        )
        for name, id_field, hash_field in _COMPONENT_SPECS
    }

    blockers = _structural_blockers(
        legacy_outputs=legacy_outputs,
        components=components,
    )

    sandbox = (
        legacy_outputs.get("actual_intake_sandbox")
        or {}
    )
    bridge = (
        legacy_outputs.get("actual_intake_bridge")
        or {}
    )

    actual_approval_present = (
        sandbox.get(
            "actual_manual_approval_submission_present"
        )
        is True
        or bridge.get(
            "actual_manual_approval_submission_present"
        )
        is True
    )

    actual_unlock_present = (
        sandbox.get(
            "actual_operator_unlock_request_present"
        )
        is True
        or bridge.get(
            "actual_operator_unlock_request_present"
        )
        is True
    )

    phase7_review_possible = (
        bridge.get("phase7_entry_review_possible")
        is True
    )

    if blockers:
        state = STATE_BLOCKED
        status = STATUS_BLOCKED_REVIEW_ONLY
        next_action = (
            "resolve_readiness_review_structural_blockers"
        )
    elif (
        actual_approval_present
        and actual_unlock_present
        and phase7_review_possible
    ):
        state = STATE_ACTUAL_INTAKE_REVIEW_ONLY
        status = (
            STATUS_ACTUAL_INTAKE_RECORDED_REVIEW_ONLY
        )
        next_action = (
            "manual_phase7_design_review_only_"
            "keep_executor_disabled"
        )
    else:
        state = STATE_WAITING_FOR_MANUAL_ARTIFACTS
        status = STATUS_WAITING_REVIEW_ONLY
        next_action = (
            "human_review_then_create_manual_approval_"
            "and_operator_unlock_artifacts"
        )

    seed = {
        "version": READINESS_REVIEW_VERSION,
        "state": state,
        "component_ids": {
            name: projection.get("source_id")
            for name, projection in components.items()
        },
        "created_at_utc": created,
    }

    report: dict[str, Any] = {
        "readiness_review_id": stable_id(
            "readiness_review",
            seed,
            24,
        ),
        "readiness_review_version": (
            READINESS_REVIEW_VERSION
        ),
        "status": status,
        "readiness_state": state,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "signed_testnet_preparation_review_only": True,
        "manual_approval_required": True,
        "operator_unlock_required": True,
        "actual_manual_approval_submission_present": (
            actual_approval_present
        ),
        "actual_operator_unlock_request_present": (
            actual_unlock_present
        ),
        "phase7_entry_review_possible": (
            phase7_review_possible
        ),
        "components": components,
        "blockers": blockers,
        "next_action": next_action,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "approval_intake_validated": False,
        "operator_unlock_request_validated": False,
        "signed_testnet_preparation_ready": False,
        "signed_testnet_readiness_passed": False,
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }

    report["readiness_review_sha256"] = (
        sha256_json(report)
    )
    return report


def run_readiness_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    preparation_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    template_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    fixture_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    gate_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    packet_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    sandbox_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
    bridge_runner: Callable[
        ...,
        Mapping[str, Any],
    ] | None = None,
) -> dict[str, Any]:
    """Run the historical Phase 6 chain behind one semantic entry point."""

    cfg = cfg or load_config(project_root)

    if preparation_runner is None:
        from crypto_ai_system.governance.signed_testnet_preparation import (
            persist_phase6_signed_testnet_preparation_preview_report,
        )

        preparation_runner = (
            persist_phase6_signed_testnet_preparation_preview_report
        )

    if template_runner is None:
        from crypto_ai_system.governance.operator_unlock_template import (
            persist_phase6_1_signed_testnet_operator_unlock_request_template_report,
        )

        template_runner = (
            persist_phase6_1_signed_testnet_operator_unlock_request_template_report
        )

    if fixture_runner is None:
        from crypto_ai_system.governance.operator_unlock_fixtures import (
            persist_phase6_2_operator_unlock_request_fixture_validator_report,
        )

        fixture_runner = (
            persist_phase6_2_operator_unlock_request_fixture_validator_report
        )

    if gate_runner is None:
        from crypto_ai_system.governance.readiness_gate import (
            persist_phase6_3_signed_testnet_readiness_gate_review_report,
        )

        gate_runner = (
            persist_phase6_3_signed_testnet_readiness_gate_review_report
        )

    if packet_runner is None:
        from crypto_ai_system.governance.readiness_packet import (
            persist_phase6_4_signed_testnet_readiness_review_packet_report,
        )

        packet_runner = (
            persist_phase6_4_signed_testnet_readiness_review_packet_report
        )

    if sandbox_runner is None:
        from crypto_ai_system.governance.actual_intake_sandbox import (
            persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report,
        )

        sandbox_runner = (
            persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report
        )

    if bridge_runner is None:
        from crypto_ai_system.governance.actual_intake_bridge import (
            persist_phase6_6_actual_intake_validation_bridge_report,
        )

        bridge_runner = (
            persist_phase6_6_actual_intake_validation_bridge_report
        )

    preparation = dict(preparation_runner(cfg=cfg))
    template = dict(template_runner(cfg=cfg))
    fixtures = dict(fixture_runner(cfg=cfg))
    gate = dict(gate_runner(cfg=cfg))
    packet = dict(packet_runner(cfg=cfg))
    sandbox = dict(sandbox_runner(cfg=cfg))
    bridge = dict(bridge_runner(cfg=cfg))

    legacy_outputs = {
        "preparation_preview": preparation,
        "operator_unlock_template": template,
        "operator_unlock_fixtures": fixtures,
        "readiness_gate": gate,
        "readiness_packet": packet,
        "actual_intake_sandbox": sandbox,
        "actual_intake_bridge": bridge,
    }

    report = build_readiness_review_report(
        legacy_outputs=legacy_outputs,
    )

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg)

    atomic_write_json(
        latest / "readiness_review_report.json",
        report,
    )
    atomic_write_json(
        storage / "readiness_review_report.json",
        report,
    )

    return {
        "report": report,
        "legacy_outputs": legacy_outputs,
    }


def run_readiness_review_latest(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    return run_readiness_review_chain(
        cfg=cfg,
        project_root=project_root,
    )["report"]


__all__ = [
    "READINESS_REVIEW_VERSION",
    "STATE_WAITING_FOR_MANUAL_ARTIFACTS",
    "STATE_ACTUAL_INTAKE_REVIEW_ONLY",
    "STATE_BLOCKED",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_ACTUAL_INTAKE_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_readiness_review_report",
    "run_readiness_review_chain",
    "run_readiness_review_latest",
]
