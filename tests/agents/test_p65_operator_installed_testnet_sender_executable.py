from __future__ import annotations
from dataclasses import replace
from pathlib import Path

from crypto_ai_system.execution.operator_installed_testnet_sender_executable import persist_p65_operator_installed_testnet_sender_executable
from external_runtime_packages.binance_futures_testnet_adapter import (
    EXACT_P65_OPERATOR_PHRASE,
    P65OperatorActivation,
    P65OrderTestIntent,
    P65SenderExecutablePolicy,
    STATUS_P65_VALIDATED_DISABLED,
    build_p65_negative_fixture_results,
    build_p65_no_network_sender_executable_self_test,
    build_p65_operator_installed_sender_executable_report,
    build_p65_signed_query_preview,
    validate_p65_activation,
    validate_p65_intent,
    validate_p65_policy,
)


def test_p65_policy_defaults_disabled_and_testnet_only():
    p = P65SenderExecutablePolicy().to_dict()
    v = validate_p65_policy(p)
    assert v["p65_policy_valid"] is True
    assert p["executable_enabled"] is False
    assert p["base_url"] == "https://demo-fapi.binance.com"
    assert p["path"] == "/fapi/v1/order/test"


def test_p65_policy_blocks_enable_and_mainnet():
    p = replace(P65SenderExecutablePolicy(), executable_enabled=True, base_url="https://fapi.binance.com").to_dict()
    v = validate_p65_policy(p)
    assert v["p65_policy_valid"] is False
    assert "P65_POLICY_EXPECTED_FALSE:executable_enabled" in v["p65_policy_block_reasons"]
    assert "P65_POLICY_BASE_URL_NOT_TESTNET" in v["p65_policy_block_reasons"]


def test_p65_activation_template_disabled():
    a = P65OperatorActivation().to_dict()
    v = validate_p65_activation(a)
    assert v["p65_activation_valid"] is True
    assert a["approval_granted"] is False
    assert a["operator_confirmation_sha256"]


def test_p65_activation_blocks_bad_phrase_and_runtime_authority():
    a = replace(P65OperatorActivation(), operator_phrase="BAD", runtime_authority_granted=True).to_dict()
    v = validate_p65_activation(a)
    assert v["p65_activation_valid"] is False
    assert "P65_OPERATOR_PHRASE_MISMATCH" in v["p65_activation_block_reasons"]
    assert "P65_ACTIVATION_EXPECTED_FALSE:runtime_authority_granted" in v["p65_activation_block_reasons"]


def test_p65_approved_activation_requires_scope():
    a = replace(P65OperatorActivation(), approval_granted=True, execution_scope="wrong").to_dict()
    v = validate_p65_activation(a, require_enabled=True)
    assert v["p65_activation_valid"] is False
    assert "P65_APPROVED_SCOPE_REQUIRED" in v["p65_activation_block_reasons"]


def test_p65_intent_valid_and_hashes():
    i = P65OrderTestIntent().to_dict()
    v = validate_p65_intent(i)
    assert v["p65_intent_valid"] is True
    assert i["canonical_query_sha256"]
    assert i["order_submit_allowed"] is False


def test_p65_intent_blocks_wrong_path_symbol_and_secret():
    i = replace(P65OrderTestIntent(), path="/fapi/v1/order", symbol="ETHUSDT").to_dict()
    i["api_secret_value"] = "bad"
    v = validate_p65_intent(i)
    assert v["p65_intent_valid"] is False
    assert "P65_INTENT_PATH_NOT_ORDER_TEST" in v["p65_intent_block_reasons"]
    assert any("P65_FORBIDDEN_SECRET" in reason for reason in v["p65_intent_block_reasons"])


def test_p65_signature_preview_disabled_by_default():
    i = P65OrderTestIntent().to_dict()
    preview = build_p65_signed_query_preview(i)
    assert preview["signature_preview_created"] is False
    assert preview["signature_created"] is False


def test_p65_signature_preview_demo_only_redacted():
    i = P65OrderTestIntent().to_dict()
    preview = build_p65_signed_query_preview(i, demo_secret="demo", allow_signature=True)
    assert preview["signature_preview_created"] is True
    assert preview["raw_signature_persisted"] is False
    assert "signature_sha256" in preview


def test_p65_no_network_self_test(tmp_path: Path):
    result = build_p65_no_network_sender_executable_self_test(tmp_path)
    assert result["no_network_self_test_passed"] is True
    assert result["http_request_sent"] is False
    assert result["signature_created"] is False
    assert result["secret_value_accessed"] is False


def test_p65_negative_fixtures_all_blocked():
    result = build_p65_negative_fixture_results()
    assert result["all_negative_fixtures_blocked"] is True
    assert len(result["cases"]) == 10


def test_p65_report_validated_disabled():
    report = build_p65_operator_installed_sender_executable_report()
    assert report["status"] == STATUS_P65_VALIDATED_DISABLED
    assert report["no_network_sender_executable_self_test_passed"] is True
    assert report["actual_order_submission_performed"] is False


def test_p65_persist_outputs(tmp_path: Path):
    (tmp_path / "storage" / "latest").mkdir(parents=True)
    report = persist_p65_operator_installed_testnet_sender_executable(tmp_path)
    assert report["status"] == STATUS_P65_VALIDATED_DISABLED
    assert (tmp_path / "storage" / "latest" / "p65_operator_installed_testnet_sender_executable_report.json").exists()
    assert (tmp_path / "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_REPORT.md").exists()
