from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_evidence_import_validator import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    ExternalEvidenceImportManifestTemplate,
    P7ImportPreviewTemplate,
    build_p50_external_evidence_import_validator_report,
    build_p50_negative_fixture_results,
    build_p7_input_preview_from_bundle,
    persist_p50_external_evidence_import_validator,
    validate_execution_transcript_for_import,
    validate_import_manifest_template,
    validate_import_paths,
    validate_no_secret_log_scan_report,
    validate_p49_handoff_source,
    validate_p7_import_preview_template,
    validate_redacted_submit_response_bundle_for_import,
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


def _write_p49_ready(root: Path, *, p49_hash: str = "9" * 64) -> None:
    atomic_write_json(
        root / "storage" / "latest" / "p49_external_runtime_evidence_handoff_report.json",
        {
            "artifact_type": "p49_external_runtime_evidence_handoff_report",
            "status": "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT",
            "review_only": True,
            "handoff_skeleton_only": True,
            "external_runtime_only": True,
            "review_package_default_no_submit": True,
            "runtime_authority_source": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "p49_external_runtime_evidence_handoff_sha256": p49_hash,
        },
    )


def _valid_bundle() -> dict:
    h = "a" * 64
    return {
        "evidence_origin": "real_signed_testnet_external_runtime",
        "environment": "testnet",
        "venue": "extended_starknet_sepolia",
        "symbol": "BTC-USD",
        "order_count": 1,
        "exchange_order_id": "testnet_order_12345",
        "client_order_id": "client_order_12345",
        "idempotency_key": "idem_12345",
        "request_hash": h,
        "exchange_response_hash": h,
        "raw_exchange_response_redacted_path": "EXTERNAL_RUNTIME_OUTPUT/redacted_submit_response.json",
        "raw_exchange_response_redacted_sha256": h,
        "hot_path_preorder_risk_gate_id": "risk_gate_12345",
        "hot_path_preorder_risk_gate_hash": h,
        "secret_reference_id": "secret_ref_metadata_only",
        "key_fingerprint_sha256": h,
        "no_secret_logged_evidence_hash": h,
        "status_polling_evidence_hash": h,
        "cancel_boundary_evidence_hash": h,
        "reconciliation_evidence_hash": h,
        "session_close_evidence_hash": h,
        "source_p6_submit_runtime_action_sha256": h,
        "raw_exchange_payload_included": False,
        "raw_request_body_included": False,
        "raw_signed_payload_included": False,
        "secret_value_included": False,
        "unredacted_exchange_response_included": False,
        "runtime_authority_granted_by_bundle": False,
        "p7_valid_status_granted_by_bundle": False,
        "live_canary_allowed_by_bundle": False,
        "live_scaled_allowed_by_bundle": False,
    }


def _valid_transcript() -> dict:
    h = "b" * 64
    return {
        "evidence_origin": "real_signed_testnet_external_runtime",
        "environment": "testnet",
        "venue": "extended_starknet_sepolia",
        "symbol": "BTC-USD",
        "operator_arming_reference": "operator_arming_ref_12345",
        "p6_external_runtime_preflight_report_hash": h,
        "p48_connector_request_hash": h,
        "hot_path_preorder_risk_gate_hash": h,
        "idempotency_key": "idem_12345",
        "redacted_submit_response_hash": h,
        "status_polling_hash_chain": [h],
        "reconciliation_summary_hash": h,
        "session_close_summary_hash": h,
        "no_secret_log_scan_report_hash": h,
        "raw_secret_values_included": False,
        "raw_signed_payload_included": False,
        "raw_request_body_included": False,
        "raw_exchange_payload_included": False,
        "unredacted_exchange_response_included": False,
        "review_package_endpoint_call_performed": False,
        "review_package_signature_created": False,
        "review_package_secret_accessed": False,
        "can_grant_runtime_authority": False,
    }


def _valid_log_scan() -> dict:
    return {
        "scan_scope": "external_runtime_redacted_logs",
        "scanned_file_count": 2,
        "forbidden_pattern_match_count": 0,
        "raw_secret_value_match_count": 0,
        "secret_field_match_count": 0,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "private_key_logged": False,
        "passphrase_logged": False,
        "secret_value_logged": False,
        "no_secret_logged_evidence_hash": "c" * 64,
        "can_grant_runtime_authority": False,
    }


def test_p50_ready_review_only_no_submit_when_p49_ready(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p49_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p50_external_evidence_import_validator_report(cfg=cfg)

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["blocked"] is False
    assert report["import_validator_skeleton_only"] is True
    assert report["candidate_import_payload_supplied"] is False
    assert report["p7_intake_execution_performed"] is False
    assert report["p7_valid_status_written_by_p50"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p50_blocks_when_p49_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p50_external_evidence_import_validator_report(cfg=cfg)

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P50_P49_HANDOFF_ARTIFACT_TYPE_INVALID" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p50_validates_p49_source_no_submit() -> None:
    invalid = validate_p49_handoff_source(
        {
            "artifact_type": "p49_external_runtime_evidence_handoff_report",
            "status": "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT",
            "review_only": True,
            "handoff_skeleton_only": True,
            "external_runtime_only": True,
            "review_package_default_no_submit": True,
            "runtime_authority_source": True,
            "actual_order_submission_performed": False,
            "order_endpoint_called": True,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
        }
    )
    assert invalid["p49_handoff_source_valid"] is False
    assert "P50_P49_HANDOFF_RUNTIME_AUTHORITY_SOURCE_NOT_FALSE" in invalid["p49_handoff_source_block_reasons"]
    assert "P50_P49_HANDOFF_ORDER_ENDPOINT_CALLED_NOT_FALSE" in invalid["p49_handoff_source_block_reasons"]


def test_p50_manifest_template_blocks_runtime_authority_and_raw_payloads() -> None:
    invalid = validate_import_manifest_template(
        ExternalEvidenceImportManifestTemplate(
            can_grant_runtime_authority=True,
            raw_signed_payload_allowed=True,
            order_endpoint_call_performed_by_importer=True,
        )
    )
    reasons = invalid["import_manifest_template_block_reasons"]
    assert invalid["import_manifest_template_valid"] is False
    assert "P50_IMPORT_MANIFEST_CAN_GRANT_RUNTIME_AUTHORITY_NOT_FALSE" in reasons
    assert "P50_IMPORT_MANIFEST_RAW_SIGNED_PAYLOAD_ALLOWED_NOT_FALSE" in reasons
    assert "P50_IMPORT_MANIFEST_ORDER_ENDPOINT_CALL_PERFORMED_BY_IMPORTER_NOT_FALSE" in reasons


def test_p50_import_paths_block_absolute_traversal_and_secret_named_paths() -> None:
    invalid = validate_import_paths(
        {
            "redacted_submit_response_bundle_path": "/tmp/redacted_submit_response_bundle.json",
            "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/../leak.json",
            "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/secret_dump.json",
            "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
            "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
            "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
            "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
        }
    )
    reasons = invalid["import_paths_block_reasons"]
    assert invalid["import_paths_valid"] is False
    assert any("P50_IMPORT_PATH_ABSOLUTE_NOT_ALLOWED" in reason for reason in reasons)
    assert any("P50_IMPORT_PATH_TRAVERSAL_NOT_ALLOWED" in reason for reason in reasons)
    assert any("P50_IMPORT_PATH_SECRET_NAMING_NOT_ALLOWED" in reason for reason in reasons)


def test_p50_bundle_import_accepts_valid_redacted_external_runtime_bundle() -> None:
    valid = validate_redacted_submit_response_bundle_for_import(_valid_bundle())
    assert valid["redacted_submit_response_bundle_import_valid"] is True
    assert valid["exchange_order_id_present"] is True


def test_p50_bundle_import_blocks_binance_reference_evidence_for_extended_primary() -> None:
    invalid = validate_redacted_submit_response_bundle_for_import(
        {**_valid_bundle(), "venue": "binance_futures_testnet", "symbol": "BTCUSDT"}
    )
    assert invalid["redacted_submit_response_bundle_import_valid"] is False
    assert "P50_BUNDLE_VENUE_NOT_TESTNET_SCOPED" in invalid["redacted_submit_response_bundle_import_block_reasons"]


def test_p50_bundle_import_blocks_mainnet_mock_order_missing_hash_and_secret_field() -> None:
    invalid = validate_redacted_submit_response_bundle_for_import(
        {
            **_valid_bundle(),
            "environment": "mainnet",
            "venue": "binance_mainnet",
            "exchange_order_id": "mock_order_123",
            "request_hash": "not-a-hash",
            "api_secret": "redacted-but-field-forbidden",
        }
    )
    reasons = invalid["redacted_submit_response_bundle_import_block_reasons"]
    assert invalid["redacted_submit_response_bundle_import_valid"] is False
    assert "P50_BUNDLE_ENVIRONMENT_NOT_TESTNET" in reasons
    assert "P50_BUNDLE_EXCHANGE_ORDER_ID_LOOKS_MOCK_OR_FIXTURE" in reasons
    assert "P50_BUNDLE_REQUEST_HASH_NOT_SHA256_HEX" in reasons
    assert "P50_FORBIDDEN_IMPORT_PAYLOAD_KEY_PRESENT:api_secret" in reasons


def test_p50_log_scan_report_blocks_secret_match_and_authority() -> None:
    invalid = validate_no_secret_log_scan_report(
        {**_valid_log_scan(), "forbidden_pattern_match_count": 1, "can_grant_runtime_authority": True}
    )
    reasons = invalid["no_secret_log_scan_report_block_reasons"]
    assert invalid["no_secret_log_scan_report_valid"] is False
    assert "P50_LOG_SCAN_FORBIDDEN_PATTERN_MATCH_COUNT_NONZERO" in reasons
    assert "P50_LOG_SCAN_CAN_GRANT_RUNTIME_AUTHORITY_NOT_FALSE" in reasons


def test_p50_transcript_blocks_review_package_endpoint_call() -> None:
    invalid = validate_execution_transcript_for_import(
        {**_valid_transcript(), "review_package_endpoint_call_performed": True, "raw_signed_payload_included": True}
    )
    reasons = invalid["execution_transcript_import_block_reasons"]
    assert invalid["execution_transcript_import_valid"] is False
    assert "P50_TRANSCRIPT_REVIEW_PACKAGE_ENDPOINT_CALL_PERFORMED_NOT_FALSE" in reasons
    assert "P50_TRANSCRIPT_RAW_SIGNED_PAYLOAD_INCLUDED_NOT_FALSE" in reasons


def test_p50_preview_template_cannot_run_p7_or_write_valid_status() -> None:
    invalid = validate_p7_import_preview_template(
        P7ImportPreviewTemplate(p7_intake_execution_performed=True, p7_valid_status_written_by_p50=True)
    )
    reasons = invalid["p7_import_preview_template_block_reasons"]
    assert invalid["p7_import_preview_template_valid"] is False
    assert "P50_P7_PREVIEW_P7_INTAKE_EXECUTION_PERFORMED_NOT_FALSE" in reasons
    assert "P50_P7_PREVIEW_P7_VALID_STATUS_WRITTEN_BY_P50_NOT_FALSE" in reasons


def test_p50_builds_p7_input_preview_without_submission_flags() -> None:
    preview = build_p7_input_preview_from_bundle(_valid_bundle())
    assert preview["p7_input_preview_only"] is True
    assert preview["p7_intake_execution_performed"] is False
    assert preview["p7_valid_status_written_by_p50"] is False
    assert preview["order_endpoint_called_by_p50"] is False
    assert preview["secret_value_accessed_by_p50"] is False
    assert preview["exchange_order_id"] == "testnet_order_12345"


def test_p50_candidate_bundle_report_builds_preview_but_remains_no_submit(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p49_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p50_external_evidence_import_validator_report(
        cfg=cfg,
        candidate_bundle=_valid_bundle(),
        candidate_transcript=_valid_transcript(),
        candidate_log_scan_report=_valid_log_scan(),
    )

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["candidate_import_payload_supplied"] is True
    assert report["import_validator_skeleton_only"] is False
    assert report["p7_input_preview"] is not None
    assert report["p7_intake_execution_performed"] is False
    assert report["p7_valid_status_written_by_p50"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p50_persist_writes_report_templates_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p49_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_p50_external_evidence_import_validator(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p50_external_evidence_import_validator_summary.json", default={})
    negative = read_json(latest / "p50_external_evidence_import_validator_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert (latest / "p50_external_evidence_import_validator_report.json").exists()
    assert (latest / "p50_external_evidence_import_manifest_TEMPLATE_NO_SUBMIT.json").exists()
    assert (latest / "p50_p7_import_preview_TEMPLATE_NO_SUBMIT.json").exists()
    assert (latest / "p50_external_evidence_import_validator_registry_record.json").exists()
    assert summary["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert summary["p7_intake_execution_performed"] is False
    assert summary["p7_valid_status_written_by_p50"] is False
    assert summary["actual_order_submission_performed"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p50_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p49_ready(tmp_path)
    cfg = load_config(tmp_path)

    negative = build_p50_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert set(negative["fixture_results"]) >= {
        "mainnet_bundle",
        "bundle_secret_field_present",
        "bundle_hash_missing",
        "absolute_import_path",
        "path_traversal",
        "log_scan_nonzero",
        "transcript_runtime_authority",
        "p7_preview_status_mutation",
    }
