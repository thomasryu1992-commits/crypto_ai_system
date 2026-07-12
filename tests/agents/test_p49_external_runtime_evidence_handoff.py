from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.external_runtime_evidence_handoff import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    ExternalRuntimeExecutionTranscriptSchema,
    NoSecretLogScanTemplate,
    P7IntakeBridgeTemplate,
    RedactedSubmitResponseBundleTemplate,
    build_p49_external_runtime_evidence_handoff_report,
    build_p49_negative_fixture_results,
    persist_p49_external_runtime_evidence_handoff,
    scan_log_text_for_secret_leaks,
    validate_execution_transcript_schema,
    validate_no_secret_log_scan_template,
    validate_p48_connector_source,
    validate_p7_intake_bridge_template,
    validate_redacted_submit_response_bundle_template,
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


def _write_p48_ready(root: Path) -> None:
    atomic_write_json(
        root / "storage" / "latest" / "p48_local_runtime_adapter_connector_report.json",
        {
            "artifact_type": "p48_local_runtime_adapter_connector_report",
            "status": "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT",
            "review_package_default_no_submit": True,
            "connector_design_only": True,
            "connector_can_be_attached_by_this_package": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "p48_local_runtime_adapter_connector_sha256": "a" * 64,
        },
    )


def test_p49_ready_review_only_no_submit(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p48_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p49_external_runtime_evidence_handoff_report(cfg=cfg)

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["blocked"] is False
    assert report["handoff_skeleton_only"] is True
    assert report["external_runtime_only"] is True
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p49_blocks_when_p48_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p49_external_runtime_evidence_handoff_report(cfg=cfg)

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P49_P48_CONNECTOR_ARTIFACT_TYPE_INVALID" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p49_validates_p48_source_must_be_no_submit() -> None:
    invalid = validate_p48_connector_source(
        {
            "artifact_type": "p48_local_runtime_adapter_connector_report",
            "status": "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT",
            "review_package_default_no_submit": True,
            "connector_design_only": True,
            "connector_can_be_attached_by_this_package": True,
            "actual_order_submission_performed": False,
            "order_endpoint_called": True,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
        }
    )

    assert invalid["p48_connector_source_valid"] is False
    assert "P49_P48_CONNECTOR_CAN_ATTACH_BY_THIS_PACKAGE" in invalid["p48_connector_source_block_reasons"]
    assert "P49_P48_CONNECTOR_ORDER_ENDPOINT_CALLED_NOT_FALSE" in invalid["p48_connector_source_block_reasons"]


def test_p49_bundle_template_blocks_mainnet_raw_payload_and_secret_field() -> None:
    invalid = validate_redacted_submit_response_bundle_template(
        {
            **RedactedSubmitResponseBundleTemplate().to_dict(),
            "environment": "mainnet",
            "venue": "binance_mainnet",
            "raw_exchange_payload_included_in_review_package": True,
            "api_secret": "raw-secret-value",
        }
    )

    reasons = invalid["redacted_submit_response_bundle_template_block_reasons"]
    assert invalid["redacted_submit_response_bundle_template_valid"] is False
    assert "P49_BUNDLE_ENVIRONMENT_NOT_TESTNET" in reasons
    assert "P49_BUNDLE_RAW_EXCHANGE_PAYLOAD_INCLUDED_IN_REVIEW_PACKAGE_NOT_FALSE" in reasons
    assert "P49_BUNDLE_FORBIDDEN_SECRET_FIELD_PRESENT:api_secret" in reasons


def test_p49_transcript_schema_blocks_runtime_authority_and_review_endpoint_call() -> None:
    invalid = validate_execution_transcript_schema(
        ExternalRuntimeExecutionTranscriptSchema(
            can_grant_runtime_authority=True,
            order_endpoint_call_performed_by_review_package=True,
            raw_signed_payload_allowed=True,
        )
    )

    reasons = invalid["execution_transcript_schema_block_reasons"]
    assert invalid["execution_transcript_schema_valid"] is False
    assert "P49_TRANSCRIPT_CAN_GRANT_RUNTIME_AUTHORITY" in reasons
    assert "P49_TRANSCRIPT_ORDER_ENDPOINT_CALL_PERFORMED_BY_REVIEW_PACKAGE_NOT_FALSE" in reasons
    assert "P49_TRANSCRIPT_RAW_SIGNED_PAYLOAD_ALLOWED_NOT_FALSE" in reasons


def test_p49_log_scan_template_and_text_scanner() -> None:
    valid = validate_no_secret_log_scan_template(NoSecretLogScanTemplate())
    assert valid["no_secret_log_scan_template_valid"] is True

    detected = scan_log_text_for_secret_leaks("INFO ok\nBINANCE_API_SECRET=abc123\n")
    assert detected["secret_leak_detected"] is True
    assert "BINANCE_API_SECRET=" in detected["matched_patterns"]

    clean = scan_log_text_for_secret_leaks("INFO redacted_key_ref=metadata-only\n")
    assert clean["secret_leak_detected"] is False


def test_p49_p7_bridge_template_cannot_submit_or_grant_authority() -> None:
    invalid = validate_p7_intake_bridge_template(
        P7IntakeBridgeTemplate(can_grant_runtime_authority=True, no_order_submission_performed_by_bridge=False)
    )

    reasons = invalid["p7_intake_bridge_template_block_reasons"]
    assert invalid["p7_intake_bridge_template_valid"] is False
    assert "P49_P7_BRIDGE_CAN_GRANT_RUNTIME_AUTHORITY" in reasons
    assert "P49_P7_BRIDGE_ORDER_SUBMISSION_PERFORMED" in reasons


def test_p49_persist_writes_report_templates_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p48_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_p49_external_runtime_evidence_handoff(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p49_external_runtime_evidence_handoff_summary.json", default={})
    negative = read_json(latest / "p49_external_runtime_evidence_handoff_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert (latest / "p49_external_runtime_evidence_handoff_report.json").exists()
    assert (latest / "p49_redacted_submit_response_bundle_TEMPLATE_NO_SUBMIT.json").exists()
    assert (latest / "p49_external_runtime_execution_transcript_SCHEMA_NO_SUBMIT.json").exists()
    assert (latest / "p49_no_secret_log_scan_TEMPLATE.json").exists()
    assert (latest / "p49_p7_intake_bridge_TEMPLATE_NO_SUBMIT.json").exists()
    assert (latest / "p49_external_runtime_evidence_handoff_registry_record.json").exists()
    assert summary["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert summary["actual_order_submission_performed"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p49_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p48_ready(tmp_path)
    cfg = load_config(tmp_path)

    negative = build_p49_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert negative["secret_scan_negative_fixture"]["secret_leak_detected"] is True
    assert "P49_BUNDLE_ENVIRONMENT_NOT_TESTNET" in negative["fixture_results"]["mainnet_bundle"]["block_reasons"]
    assert "P49_P7_BRIDGE_ORDER_SUBMISSION_PERFORMED" in negative["fixture_results"]["p7_bridge_order_submission_performed"]["block_reasons"]
