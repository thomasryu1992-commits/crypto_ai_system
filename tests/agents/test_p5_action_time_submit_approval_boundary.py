from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.action_time_submit_approval_boundary import (
    EXPLICIT_APPROVAL_PHRASE,
    ActionTimeRuntimeFreshnessEvidence,
    ActionTimeSubmitApprovalEvidence,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_VALID_REVIEW_ONLY,
    build_action_time_submit_approval_boundary_report,
    build_p5_negative_fixture_results,
    persist_action_time_submit_approval_boundary,
    validate_action_time_runtime_freshness,
    validate_action_time_submit_approval_evidence,
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


def _write_p4_ready(root: Path, *, p4_hash: str = "a" * 64) -> None:
    latest = root / "storage" / "latest"
    report = {
        "status": "P4_SIGNED_TESTNET_ONE_ORDER_RUNTIME_PACKAGE_READY_REVIEW_ONLY_DISABLED",
        "runtime_package_ready_for_separate_operator_submit_action_review_only": True,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "order_endpoint_called": False,
        "testnet_order_submission_allowed": False,
        "secret_value_accessed": False,
        "p4_signed_testnet_runtime_package_id": "p4_runtime_1",
        "p4_signed_testnet_runtime_package_sha256": p4_hash,
    }
    atomic_write_json(latest / "p4_signed_testnet_one_order_runtime_package_report.json", report)


def test_p5_valid_review_only_boundary_never_submits(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p4_ready(tmp_path, p4_hash="b" * 64)
    cfg = load_config(tmp_path)

    report = build_action_time_submit_approval_boundary_report(
        cfg=cfg,
        intent=OneOrderRuntimeIntent(
            idempotency_key="p5_valid_idem",
            approval_packet_id="approval_packet_1",
            approval_intake_id="approval_intake_1",
            risk_gate_id="risk_gate_1",
            order_intent_id="order_intent_1",
        ),
        approval_evidence=ActionTimeSubmitApprovalEvidence(source_p4_runtime_package_sha256="b" * 64),
        freshness_evidence=ActionTimeRuntimeFreshnessEvidence(),
        secret_binding=RuntimeSecretBindingMetadata(secret_reference_id="ref", key_fingerprint_sha256="c" * 64),
    )

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["action_time_submit_approval_boundary_valid_review_only"] is True
    assert report["action_time_submit_preconditions_valid_review_only"] is True
    assert report["does_not_grant_submit_permission"] is True
    assert report["separate_runtime_submit_action_required"] is True
    assert report["testnet_order_submission_allowed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["secret_value_accessed"] is False
    assert report["unsafe_truthy_execution_flags"] == []


def test_p5_blocks_without_p4_ready(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)

    report = build_action_time_submit_approval_boundary_report(
        cfg=cfg,
        approval_evidence=ActionTimeSubmitApprovalEvidence(source_p4_runtime_package_sha256="d" * 64),
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "P5_P4_RUNTIME_PACKAGE_STATUS_NOT_READY" in report["block_reasons"]
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_p5_approval_evidence_requires_exact_phrase_and_p4_hash() -> None:
    result = validate_action_time_submit_approval_evidence(
        {
            "operator_id": "operator",
            "approval_ticket_id": "ticket",
            "explicit_approval_text": "approve one order",
            "max_order_count": 1,
            "testnet_only": True,
            "single_order_scope": True,
            "no_auto_generated_approval_file": True,
            "human_operator_submitted": True,
            "runtime_submit_action_is_separate": True,
            "source_p4_runtime_package_sha256": "x" * 64,
        },
        expected_p4_sha256="e" * 64,
    )

    assert result["action_time_submit_approval_evidence_valid"] is False
    assert "P5_EXPLICIT_ACTION_TIME_APPROVAL_PHRASE_MISSING_OR_MISMATCHED" in result["approval_evidence_block_reasons"]
    assert "P5_SOURCE_P4_RUNTIME_PACKAGE_HASH_MISMATCH" in result["approval_evidence_block_reasons"]

    valid = validate_action_time_submit_approval_evidence(
        ActionTimeSubmitApprovalEvidence(explicit_approval_text=EXPLICIT_APPROVAL_PHRASE, source_p4_runtime_package_sha256="e" * 64),
        expected_p4_sha256="e" * 64,
    )
    assert valid["action_time_submit_approval_evidence_valid"] is True


def test_p5_runtime_freshness_blocks_stale_duplicate_and_kill_switch() -> None:
    stale = validate_action_time_runtime_freshness(ActionTimeRuntimeFreshnessEvidence(hot_path_preorder_risk_gate_age_sec=120))
    duplicate = validate_action_time_runtime_freshness(ActionTimeRuntimeFreshnessEvidence(idempotency_key_already_seen=True))
    kill = validate_action_time_runtime_freshness(ActionTimeRuntimeFreshnessEvidence(config_kill_switch_enabled=True))

    assert "P5_HOT_PATH_PREORDER_RISK_GATE_STALE_AT_ACTION_TIME" in stale["runtime_freshness_block_reasons"]
    assert "P5_IDEMPOTENCY_KEY_ALREADY_SEEN" in duplicate["runtime_freshness_block_reasons"]
    assert "P5_CONFIG_KILL_SWITCH_ENABLED" in kill["runtime_freshness_block_reasons"]


def test_p5_persist_writes_report_summary_registry_and_negative_fixtures(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p4_ready(tmp_path, p4_hash="f" * 64)
    cfg = load_config(tmp_path)

    report = persist_action_time_submit_approval_boundary(cfg=cfg)
    latest = tmp_path / "storage" / "latest"
    summary = read_json(latest / "p5_action_time_submit_approval_boundary_summary.json", default={})
    negative = read_json(latest / "p5_action_time_submit_approval_boundary_negative_fixture_results.json", default={})

    assert report["status"] == STATUS_VALID_REVIEW_ONLY
    assert (latest / "p5_action_time_submit_approval_boundary_report.json").exists()
    assert (latest / "p5_action_time_submit_approval_boundary_registry_record.json").exists()
    assert summary["action_time_submit_approval_boundary_valid_review_only"] is True
    assert summary["actual_order_submission_performed"] is False
    assert summary["order_endpoint_called"] is False
    assert summary["secret_value_accessed"] is False
    assert summary["negative_fixtures_all_blocked"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True


def test_p5_negative_fixture_builder_blocks_all_cases(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    _write_p4_ready(tmp_path, p4_hash="1" * 64)
    cfg = load_config(tmp_path)

    negative = build_p5_negative_fixture_results(cfg=cfg)

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert negative["actual_order_submission_performed"] is False
    assert negative["order_endpoint_called"] is False
    assert negative["secret_value_accessed"] is False
    assert "P5_EXPLICIT_ACTION_TIME_APPROVAL_PHRASE_MISSING_OR_MISMATCHED" in negative["fixture_results"]["missing_explicit_approval_phrase"]["block_reasons"]
    assert "P5_IDEMPOTENCY_KEY_ALREADY_SEEN" in negative["fixture_results"]["duplicate_idempotency"]["block_reasons"]
