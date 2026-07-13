from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.signed_testnet_one_order_runtime_package import (
    RuntimeSecretBindingMetadata,
    OneOrderRuntimeIntent,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_READY_REVIEW_ONLY,
    build_p4_negative_fixture_results,
    build_signed_testnet_one_order_runtime_package_report,
    persist_signed_testnet_one_order_runtime_package,
    validate_one_order_guard,
    validate_runtime_secret_binding_metadata,
)


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def _write_p4_ready_sources(root: Path) -> None:
    latest = root / "storage" / "latest"
    phase_d = {
        "status": "PHASE_D_CANDIDATE_MANUAL_APPROVAL_CHAIN_VALID_REVIEW_ONLY",
        "approval_registry_valid_review_outcome": True,
        "approval_packet_id": "approval_packet_1",
        "approval_intake_id": "approval_intake_1",
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "phase_d_candidate_manual_approval_chain_report_sha256": "phase_d_hash_1",
    }
    approval_registry = {
        "status": "APPROVAL_REGISTRY_VALID_REVIEW_ONLY",
        "validation_status": "valid_review_only_staging_approval",
        "approval_packet_id": "approval_packet_1",
        "approval_intake_id": "approval_intake_1",
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "approval_registry_record_sha256": "approval_registry_hash_1",
    }
    atomic_write_json(latest / "phase_d_candidate_manual_approval_chain_report.json", phase_d)
    atomic_write_json(latest / "approval_registry_record.json", approval_registry)


def test_p4_runtime_package_ready_review_only_never_submits(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p4_ready_sources(tmp_path)
    cfg = load_config(tmp_path)

    report = build_signed_testnet_one_order_runtime_package_report(
        cfg=cfg,
        secret_binding=RuntimeSecretBindingMetadata(
            secret_reference_id="testnet_key_ref_1",
            key_fingerprint_sha256="a" * 64,
        ),
        intent=OneOrderRuntimeIntent(
            idempotency_key="idem_p4_ready_1",
            approval_packet_id="approval_packet_1",
            approval_intake_id="approval_intake_1",
            risk_gate_id="risk_gate_1",
            order_intent_id="order_intent_1",
        ),
    )

    assert report["status"] == STATUS_READY_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["runtime_package_ready_for_separate_operator_submit_action_review_only"] is True
    assert report["runtime_package_does_not_grant_submit_permission"] is True
    assert report["testnet_order_submission_allowed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["order_status_endpoint_called"] is False
    assert report["cancel_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["signed_request_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["secret_value_logged"] is False
    assert report["unsafe_truthy_execution_flags"] == []
    assert report["endpoint_boundary_evidence"]["place_order"]["endpoint_called"] is False
    assert report["endpoint_boundary_evidence"]["place_order"]["secret_value_logged"] is False
    assert report["post_submit_relock_policy"]["signed_order_executor_enabled_after_action"] is False


def test_p4_blocks_without_phase_d_valid_approval_chain(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_signed_testnet_one_order_runtime_package_report(
        cfg=cfg,
        secret_binding=RuntimeSecretBindingMetadata(secret_reference_id="ref", key_fingerprint_sha256="b" * 64),
        intent=OneOrderRuntimeIntent(idempotency_key="missing_phase_d"),
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "P4_PHASE_D_MANUAL_APPROVAL_CHAIN_NOT_VALID" in report["block_reasons"]
    assert "P4_APPROVAL_REGISTRY_STATUS_NOT_VALID_REVIEW_ONLY" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p4_secret_binding_validation_blocks_secret_misuse() -> None:
    validation = validate_runtime_secret_binding_metadata({
        "secret_reference_id": "ref",
        "key_fingerprint_sha256": "c" * 64,
        "metadata_only": False,
        "environment": "live",
        "key_scope": "live_trade",
        "secret_value_accessed": True,
        "api_secret_value_logged": True,
        "withdrawal_permission_enabled": True,
    })

    assert validation["secret_binding_metadata_valid"] is False
    assert "P4_SECRET_BINDING_NOT_METADATA_ONLY" in validation["secret_binding_block_reasons"]
    assert "P4_SECRET_BINDING_ENVIRONMENT_NOT_TESTNET" in validation["secret_binding_block_reasons"]
    assert "P4_SECRET_BINDING_KEY_SCOPE_NOT_TESTNET_TRADE_ONLY" in validation["secret_binding_block_reasons"]
    assert "P4_SECRET_BINDING_UNSAFE_TRUE:secret_value_accessed" in validation["secret_binding_block_reasons"]
    assert "P4_SECRET_BINDING_UNSAFE_TRUE:api_secret_value_logged" in validation["secret_binding_block_reasons"]
    assert "P4_SECRET_BINDING_UNSAFE_TRUE:withdrawal_permission_enabled" in validation["secret_binding_block_reasons"]
    assert validation["secret_value_accessed"] is False
    assert validation["secret_value_logged"] is False


def test_p4_one_order_guard_blocks_duplicate_hard_cap_and_kill_switch() -> None:
    duplicate = validate_one_order_guard(
        OneOrderRuntimeIntent(idempotency_key="dupe"),
        idempotency_key="dupe",
        existing_idempotency_keys=["dupe"],
    )
    hard_cap = validate_one_order_guard(
        OneOrderRuntimeIntent(idempotency_key="cap", quantity=1.0, reference_price=50000.0, max_notional=10.0),
        idempotency_key="cap",
    )
    kill_switch = validate_one_order_guard(
        OneOrderRuntimeIntent(idempotency_key="kill", manual_kill_switch_engaged=True),
        idempotency_key="kill",
    )
    stale_risk = validate_one_order_guard(
        OneOrderRuntimeIntent(idempotency_key="stale", hot_path_preorder_risk_gate_fresh=False),
        idempotency_key="stale",
    )

    assert "P4_DUPLICATE_IDEMPOTENCY_KEY_BLOCKED" in duplicate["one_order_guard_block_reasons"]
    assert "P4_LOW_NOTIONAL_CAP_EXCEEDED" in hard_cap["one_order_guard_block_reasons"]
    assert "P4_MANUAL_KILL_SWITCH_ENGAGED" in kill_switch["one_order_guard_block_reasons"]
    assert "P4_HOT_PATH_PREORDER_RISK_GATE_NOT_FRESH" in stale_risk["one_order_guard_block_reasons"]


def test_p4_persist_writes_reports_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p4_ready_sources(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_signed_testnet_one_order_runtime_package(
        cfg=cfg,
        secret_binding=RuntimeSecretBindingMetadata(secret_reference_id="ref", key_fingerprint_sha256="d" * 64),
        intent=OneOrderRuntimeIntent(idempotency_key="persist_case"),
    )

    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p4_signed_testnet_one_order_runtime_package_summary.json", default={})
    negative = read_json(latest / "p4_signed_testnet_runtime_package_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_READY_REVIEW_ONLY
    assert (latest / "p4_signed_testnet_one_order_runtime_package_report.json").exists()
    assert (latest / "p4_signed_testnet_one_order_runtime_package_registry_record.json").exists()
    assert (latest / "p4_signed_testnet_one_order_runtime_package_summary.json").exists()
    assert summary["actual_order_submission_performed"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p4_negative_fixture_builder_blocks_all_cases() -> None:
    negative = build_p4_negative_fixture_results()

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert negative["secret_value_accessed"] is False
    assert "P4_DUPLICATE_IDEMPOTENCY_KEY_BLOCKED" in negative["fixture_results"]["duplicate_idempotency"]["one_order_guard_block_reasons"]
    assert "P4_LOW_NOTIONAL_CAP_EXCEEDED" in negative["fixture_results"]["hard_cap_exceeded"]["one_order_guard_block_reasons"]
