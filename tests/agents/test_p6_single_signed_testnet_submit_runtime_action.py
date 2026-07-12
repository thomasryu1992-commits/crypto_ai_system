from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.single_signed_testnet_submit_runtime_action import (
    P6_EXPLICIT_RUNTIME_ARMING_PHRASE,
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_DISABLED_NO_SUBMIT,
    SingleSignedTestnetRuntimeArmingEvidence,
    SingleSignedTestnetRuntimeFreshnessEvidence,
    build_p6_negative_fixture_results,
    build_single_signed_testnet_submit_runtime_action_report,
    persist_single_signed_testnet_submit_runtime_action,
    validate_exchange_submit_evidence,
    validate_runtime_arming_evidence,
    validate_runtime_freshness_evidence,
)
from crypto_ai_system.execution.signed_testnet_one_order_runtime_package import (
    OneOrderRuntimeIntent,
    RuntimeSecretBindingMetadata,
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


def _write_p5_ready(root: Path, *, p5_hash: str = "a" * 64) -> None:
    latest = root / "storage" / "latest"
    report = {
        "status": "P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VALID_REVIEW_ONLY_NO_SUBMIT",
        "action_time_submit_preconditions_valid_review_only": True,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "order_endpoint_called": False,
        "testnet_order_submission_allowed": False,
        "secret_value_accessed": False,
        "p5_action_time_submit_approval_boundary_id": "p5_boundary_1",
        "p5_action_time_submit_approval_boundary_sha256": p5_hash,
    }
    atomic_write_json(latest / "p5_action_time_submit_approval_boundary_report.json", report)


def test_p6_ready_disabled_no_submit_by_default(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p5_ready(tmp_path, p5_hash="b" * 64)
    cfg = load_config(tmp_path)

    report = build_single_signed_testnet_submit_runtime_action_report(
        cfg=cfg,
        intent=OneOrderRuntimeIntent(
            idempotency_key="p6_valid_disabled_idem",
            approval_packet_id="approval_packet_1",
            approval_intake_id="approval_intake_1",
            risk_gate_id="risk_gate_1",
            order_intent_id="order_intent_1",
        ),
        arming_evidence=SingleSignedTestnetRuntimeArmingEvidence(source_p5_action_time_boundary_sha256="b" * 64),
        freshness_evidence=SingleSignedTestnetRuntimeFreshnessEvidence(),
        secret_binding=RuntimeSecretBindingMetadata(secret_reference_id="ref", key_fingerprint_sha256="c" * 64),
    )

    assert report["status"] == STATUS_READY_DISABLED_NO_SUBMIT
    assert report["blocked"] is False
    assert report["p5_action_time_boundary_valid"] is True
    assert report["submit_requested"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["actual_testnet_order_submitted"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["signed_request_created"] is False
    assert report["real_exchange_order_id_present"] is False
    assert report["secret_value_accessed"] is False
    assert report["endpoint_submit_evidence"]["blocked_before_http"] is True
    assert report["unsafe_truthy_execution_flags"] == []


def test_p6_blocks_without_p5_ready(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_single_signed_testnet_submit_runtime_action_report(
        cfg=cfg,
        arming_evidence=SingleSignedTestnetRuntimeArmingEvidence(source_p5_action_time_boundary_sha256="d" * 64),
    )

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "P6_P5_ACTION_TIME_BOUNDARY_STATUS_NOT_VALID" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p6_runtime_arming_requires_exact_phrase_and_p5_hash() -> None:
    invalid = validate_runtime_arming_evidence(
        {
            "operator_id": "operator",
            "approval_ticket_id": "ticket",
            "explicit_runtime_arming_text": "approve",
            "local_console_confirmed": True,
            "human_operator_submitted": True,
            "testnet_only": True,
            "btcusdt_only": True,
            "max_order_count": 1,
            "low_notional_cap_confirmed": True,
            "no_auto_generated_runtime_approval_file": True,
            "understands_real_order_endpoint_may_be_called_when_armed": True,
            "source_p5_action_time_boundary_sha256": "x" * 64,
        },
        expected_p5_sha256="e" * 64,
    )
    assert invalid["runtime_arming_evidence_valid"] is False
    assert "P6_EXPLICIT_RUNTIME_ARMING_PHRASE_MISSING_OR_MISMATCHED" in invalid["runtime_arming_block_reasons"]
    assert "P6_SOURCE_P5_ACTION_TIME_BOUNDARY_HASH_MISMATCH" in invalid["runtime_arming_block_reasons"]

    valid = validate_runtime_arming_evidence(
        SingleSignedTestnetRuntimeArmingEvidence(
            explicit_runtime_arming_text=P6_EXPLICIT_RUNTIME_ARMING_PHRASE,
            source_p5_action_time_boundary_sha256="e" * 64,
        ),
        expected_p5_sha256="e" * 64,
    )
    assert valid["runtime_arming_evidence_valid"] is True


def test_p6_runtime_freshness_blocks_stale_duplicate_and_kill_switch() -> None:
    stale = validate_runtime_freshness_evidence(SingleSignedTestnetRuntimeFreshnessEvidence(hot_path_preorder_risk_gate_age_sec=120))
    duplicate = validate_runtime_freshness_evidence(SingleSignedTestnetRuntimeFreshnessEvidence(idempotency_key_already_seen=True))
    kill = validate_runtime_freshness_evidence(SingleSignedTestnetRuntimeFreshnessEvidence(config_kill_switch_enabled=True))

    assert "P6_HOT_PATH_PREORDER_RISK_GATE_STALE_AT_RUNTIME" in stale["runtime_freshness_block_reasons"]
    assert "P6_IDEMPOTENCY_KEY_ALREADY_SEEN" in duplicate["runtime_freshness_block_reasons"]
    assert "P6_CONFIG_KILL_SWITCH_ENABLED" in kill["runtime_freshness_block_reasons"]


def test_p6_submit_request_requires_operator_network_allowance_and_real_adapter(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p5_ready(tmp_path, p5_hash="f" * 64)
    cfg = load_config(tmp_path)

    no_network = build_single_signed_testnet_submit_runtime_action_report(
        cfg=cfg,
        arming_evidence=SingleSignedTestnetRuntimeArmingEvidence(
            source_p5_action_time_boundary_sha256="f" * 64,
            execute_real_submit_now=True,
            runtime_network_call_allowed_by_operator=False,
        ),
        execute_submit=True,
    )
    assert no_network["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P6_RUNTIME_NETWORK_CALL_NOT_ALLOWED_BY_OPERATOR" in no_network["block_reasons"]
    assert no_network["actual_order_submission_performed"] is False
    assert no_network["order_endpoint_called"] is False

    no_adapter = build_single_signed_testnet_submit_runtime_action_report(
        cfg=cfg,
        arming_evidence=SingleSignedTestnetRuntimeArmingEvidence(
            source_p5_action_time_boundary_sha256="f" * 64,
            execute_real_submit_now=True,
            runtime_network_call_allowed_by_operator=True,
        ),
        execute_submit=True,
    )
    assert no_adapter["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert "P6_REAL_SIGNED_TESTNET_ENDPOINT_ADAPTER_NOT_ATTACHED" in no_adapter["block_reasons"]
    assert no_adapter["actual_order_submission_performed"] is False
    assert no_adapter["order_endpoint_called"] is False


def test_p6_exchange_submit_evidence_validation_requires_real_order_id_when_real() -> None:
    invalid = validate_exchange_submit_evidence(
        {
            "order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
            "signed_request_created": True,
            "exchange_order_status": "NEW",
            "real_exchange_response": True,
            "secret_value_logged": False,
            "retry_count": 0,
        },
        require_real_exchange_response=True,
    )
    assert invalid["exchange_submit_evidence_valid"] is False
    assert "P6_EXCHANGE_ORDER_ID_MISSING" in invalid["exchange_submit_block_reasons"]

    valid = validate_exchange_submit_evidence(
        {
            "order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
            "signed_request_created": True,
            "exchange_order_id": "12345",
            "exchange_order_status": "NEW",
            "real_exchange_response": True,
            "secret_value_logged": False,
            "retry_count": 0,
        },
        require_real_exchange_response=True,
    )
    assert valid["exchange_submit_evidence_valid"] is True


def test_p6_persist_writes_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p5_ready(tmp_path, p5_hash="1" * 64)
    cfg = load_config(tmp_path)

    report = persist_single_signed_testnet_submit_runtime_action(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p6_single_signed_testnet_submit_runtime_action_summary.json", default={})
    negative = read_json(latest / "p6_single_signed_testnet_submit_runtime_action_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_READY_DISABLED_NO_SUBMIT
    assert (latest / "p6_single_signed_testnet_submit_runtime_action_report.json").exists()
    assert (latest / "p6_single_signed_testnet_submit_runtime_action_registry_record.json").exists()
    assert summary["status"] == STATUS_READY_DISABLED_NO_SUBMIT
    assert summary["actual_order_submission_performed"] is False
    assert summary["actual_testnet_order_submitted"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p6_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p5_ready(tmp_path, p5_hash="2" * 64)
    cfg = load_config(tmp_path)

    negative = build_p6_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert negative["secret_value_accessed"] is False
    assert "P6_EXPLICIT_RUNTIME_ARMING_PHRASE_MISSING_OR_MISMATCHED" in negative["fixture_results"]["missing_runtime_arming_phrase"]["block_reasons"]
    assert "P6_RUNTIME_NETWORK_CALL_NOT_ALLOWED_BY_OPERATOR" in negative["fixture_results"]["submit_requested_without_operator_network_allowance"]["block_reasons"]
    assert "P6_REAL_SIGNED_TESTNET_ENDPOINT_ADAPTER_NOT_ATTACHED" in negative["fixture_results"]["submit_requested_without_real_adapter"]["block_reasons"]
    assert "P6_IDEMPOTENCY_KEY_ALREADY_SEEN" in negative["fixture_results"]["duplicate_idempotency"]["block_reasons"]


def test_p6_adapter_boundary_and_external_runtime_preflight_are_recorded(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p5_ready(tmp_path, p5_hash="2" * 64)
    cfg = load_config(tmp_path)

    report = persist_single_signed_testnet_submit_runtime_action(cfg=cfg)

    assert report["adapter_boundary_validation"]["adapter_boundary_valid"] is True
    assert report["external_runtime_preflight_report"]["preflight_passed"] is True
    assert report["external_runtime_preflight_report"]["review_package_default_no_submit"] is True
    assert report["external_runtime_preflight_report"]["actual_order_submission_performed"] is False
    assert (tmp_path / "storage" / "latest" / "p6_external_runtime_preflight_report.json").exists()


def test_p6_adapter_boundary_blocks_mainnet_or_secret_accepting_adapter() -> None:
    from crypto_ai_system.execution.single_signed_testnet_submit_runtime_action import validate_signed_testnet_adapter_boundary

    invalid = validate_signed_testnet_adapter_boundary(
        {
            "adapter_id": "bad_live_adapter",
            "adapter_family": "real_endpoint_external_runtime",
            "venue": "binance_mainnet",
            "environment": "mainnet",
            "symbol_scope": "BTCUSDT_ONLY",
            "real_endpoint_adapter": True,
            "network_call_capable": True,
            "can_submit_orders_by_default": True,
            "code_path_isolated_from_review_package": False,
            "external_runtime_only": False,
            "disabled_adapter_available": False,
            "request_signing_location": "report_payload",
            "secret_values_accepted_by_report": True,
            "secret_values_logged_by_adapter": True,
            "supports_idempotency_key": False,
            "supports_duplicate_submit_lock": False,
            "supports_post_submit_relock": False,
            "supports_redacted_evidence_export": False,
        },
        submit_requested=True,
    )

    assert invalid["adapter_boundary_valid"] is False
    assert "P6_ADAPTER_ENVIRONMENT_NOT_TESTNET" in invalid["adapter_boundary_block_reasons"]
    assert "P6_ADAPTER_REPORT_ACCEPTS_SECRET_VALUES" in invalid["adapter_boundary_block_reasons"]
    assert "P6_ADAPTER_CAN_SUBMIT_BY_DEFAULT" in invalid["adapter_boundary_block_reasons"]
