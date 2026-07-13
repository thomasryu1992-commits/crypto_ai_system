from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.local_runtime_adapter_connector import (
    STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_READY_REVIEW_ONLY_NO_SUBMIT,
    LocalRuntimeAdapterConnectorConfig,
    LocalRuntimeAdapterConnectorRequestTemplate,
    build_p48_local_runtime_adapter_connector_report,
    build_p48_negative_fixture_results,
    persist_p48_local_runtime_adapter_connector,
    validate_connector_request_template,
    validate_local_runtime_adapter_connector_config,
    validate_p6_preflight_source,
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


def _write_p6_preflight_ready(root: Path) -> None:
    atomic_write_json(
        root / "storage" / "latest" / "p6_external_runtime_preflight_report.json",
        {
            "artifact_type": "p6_external_runtime_preflight_report",
            "status": "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT",
            "preflight_passed": True,
            "review_package_default_no_submit": True,
            "submit_requested": False,
            "runtime_network_call_allowed_by_operator": False,
            "actual_order_submission_performed": False,
            "actual_testnet_order_submitted": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "p6_external_runtime_preflight_report_sha256": "a" * 64,
        },
    )


def test_p48_connector_ready_review_only_no_submit(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p6_preflight_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p48_local_runtime_adapter_connector_report(cfg=cfg)

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert report["blocked"] is False
    assert report["review_package_default_no_submit"] is True
    assert report["connector_can_be_attached_by_this_package"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p48_blocks_when_p6_preflight_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_p48_local_runtime_adapter_connector_report(cfg=cfg)

    assert report["status"] == STATUS_BLOCKED_FAIL_CLOSED
    assert report["blocked"] is True
    assert "P48_P6_PREFLIGHT_ARTIFACT_TYPE_INVALID" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p48_validates_p6_preflight_must_be_no_submit() -> None:
    invalid = validate_p6_preflight_source(
        {
            "artifact_type": "p6_external_runtime_preflight_report",
            "status": "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT",
            "preflight_passed": True,
            "review_package_default_no_submit": True,
            "submit_requested": True,
            "runtime_network_call_allowed_by_operator": True,
            "actual_order_submission_performed": False,
            "actual_testnet_order_submitted": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
        }
    )

    assert invalid["p6_preflight_source_valid"] is False
    assert "P48_P6_PREFLIGHT_SUBMIT_REQUESTED" in invalid["p6_preflight_source_block_reasons"]
    assert "P48_P6_PREFLIGHT_RUNTIME_NETWORK_ALLOWED" in invalid["p6_preflight_source_block_reasons"]


def test_p48_connector_config_blocks_mainnet_network_secret_and_attached_adapter() -> None:
    invalid = validate_local_runtime_adapter_connector_config(
        {
            **LocalRuntimeAdapterConnectorConfig().to_dict(),
            "environment": "mainnet",
            "venue": "binance_mainnet",
            "network_calls_allowed_in_review_package": True,
            "real_adapter_code_included_in_review_package": True,
            "local_runtime_connector_attached": True,
            "api_secret": "raw-secret-value",
        }
    )

    assert invalid["connector_config_valid"] is False
    reasons = invalid["connector_config_block_reasons"]
    assert "P48_ENVIRONMENT_NOT_TESTNET" in reasons
    assert "P48_NETWORK_CALLS_ALLOWED_IN_REVIEW_PACKAGE" in reasons
    assert "P48_REAL_ADAPTER_CODE_INCLUDED_IN_REVIEW_PACKAGE" in reasons
    assert "P48_LOCAL_RUNTIME_CONNECTOR_ATTACHED_IN_REVIEW_PACKAGE" in reasons
    assert "P48_FORBIDDEN_SECRET_FIELD_PRESENT:api_secret" in reasons


def test_p48_request_template_cannot_grant_runtime_authority() -> None:
    invalid = validate_connector_request_template(LocalRuntimeAdapterConnectorRequestTemplate(can_grant_runtime_authority=True))
    assert invalid["connector_request_template_valid"] is False
    assert "P48_CONNECTOR_REQUEST_CAN_GRANT_RUNTIME_AUTHORITY" in invalid["connector_request_template_block_reasons"]


def test_p48_persist_writes_report_templates_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p6_preflight_ready(tmp_path)
    cfg = load_config(tmp_path)

    report = persist_p48_local_runtime_adapter_connector(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p48_local_runtime_adapter_connector_summary.json", default={})
    negative = read_json(latest / "p48_local_runtime_adapter_connector_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert (latest / "p48_local_runtime_adapter_connector_report.json").exists()
    assert (latest / "p48_local_runtime_adapter_connector_TEMPLATE_NO_SUBMIT.json").exists()
    assert (latest / "p48_operator_local_runtime_connector_request_TEMPLATE.json").exists()
    assert (latest / "p48_local_runtime_adapter_connector_registry_record.json").exists()
    assert summary["status"] == STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    assert summary["actual_order_submission_performed"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p48_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p6_preflight_ready(tmp_path)
    cfg = load_config(tmp_path)

    negative = build_p48_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert "P48_NETWORK_CALLS_ALLOWED_IN_REVIEW_PACKAGE" in negative["config_fixture_results"]["network_allowed_in_review_package"]["connector_config_block_reasons"]
    assert "P48_CONNECTOR_REQUEST_CAN_GRANT_RUNTIME_AUTHORITY" in negative["template_fixture_results"]["bad_request_template_runtime_authority"]["connector_request_template_block_reasons"]
