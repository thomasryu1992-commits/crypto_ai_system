from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.phase9_2_secret_manager_runtime_binding_design import (
    STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED,
    build_secret_manager_runtime_binding_template,
    persist_phase9_2_secret_manager_runtime_binding_report,
    validate_secret_manager_runtime_binding_template,
)


def _latest_json(name: str) -> dict:
    path = Path.cwd() / "storage" / "latest" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase9_2_secret_manager_runtime_binding_records_still_disabled_artifacts() -> None:
    report = persist_phase9_2_secret_manager_runtime_binding_report(run_endpoint_time_refresh_first=True)

    assert report["status"] == STATUS_PHASE9_2_SECRET_MANAGER_RUNTIME_BINDING_RECORDED_STILL_DISABLED
    assert report["phase9_2_secret_manager_runtime_binding_recorded"] is True
    assert report["secret_manager_runtime_binding_design_ready"] is True
    assert report["secret_manager_runtime_binding_performed"] is False
    assert report["api_secret_value_read_allowed"] is False
    assert report["signature_creation_allowed"] is False
    assert report["order_endpoint_call_allowed"] is False
    assert report["runtime_authority_granted"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["order_endpoint_called"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["block_reasons"]

    latest = Path.cwd() / "storage" / "latest"
    assert (latest / "phase9_2_secret_manager_runtime_binding_report.json").exists()
    assert (latest / "secret_manager_runtime_binding_DESIGN_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert (latest / "phase9_2_secret_manager_runtime_binding_validation_report.json").exists()
    assert (latest / "phase9_2_secret_manager_runtime_binding_negative_fixture_results.json").exists()


def test_phase9_2_secret_manager_runtime_binding_template_validates_metadata_only_fixture() -> None:
    template = _latest_json("secret_manager_runtime_binding_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    validation = validate_secret_manager_runtime_binding_template(template)

    assert validation["phase9_2_secret_manager_runtime_binding_template_valid"] is True
    assert validation["blocked"] is False
    assert validation["fail_closed"] is False
    assert validation["block_reasons"] == []


def test_phase9_2_secret_manager_runtime_binding_blocks_secret_material_and_secret_reads() -> None:
    template = _latest_json("secret_manager_runtime_binding_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    template["api_secret_value_read_allowed"] = True
    template["api_secret"] = "raw-secret-value-should-block"

    validation = validate_secret_manager_runtime_binding_template(template)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    joined = "\n".join(validation["block_reasons"])
    assert "PHASE9_2_SECRET_BINDING_SECRET_ACCESS_ALLOWED:api_secret_value_read_allowed" in joined
    assert "PHASE9_2_SECRET_BINDING_SECRET_LIKE_VALUES_PRESENT" in joined


def test_phase9_2_secret_manager_runtime_binding_blocks_runtime_binding_and_endpoint_actions() -> None:
    template = _latest_json("secret_manager_runtime_binding_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    template["secret_manager_runtime_binding_performed"] = True
    template["signature_creation_allowed"] = True
    template["order_endpoint_call_allowed"] = True
    template["order_endpoint_called"] = True
    template["signature_created"] = True

    validation = validate_secret_manager_runtime_binding_template(template)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    joined = "\n".join(validation["block_reasons"])
    assert "PHASE9_2_SECRET_BINDING_PERFORMED_UNEXPECTED" in joined
    assert "PHASE9_2_SECRET_BINDING_UNSAFE_RUNTIME_FLAG:signature_creation_allowed" in joined
    assert "PHASE9_2_SECRET_BINDING_UNSAFE_RUNTIME_FLAG:order_endpoint_call_allowed" in joined
    assert "order_endpoint_called" in joined
    assert "signature_created" in joined


def test_phase9_2_secret_manager_runtime_binding_negative_fixtures_and_registry() -> None:
    report = _latest_json("phase9_2_secret_manager_runtime_binding_report.json")
    negative = report["negative_fixture_results"]

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert len(negative["fixture_results"]) >= 18
    for fixture in negative["fixture_results"].values():
        assert fixture["blocked"] is True
        assert fixture["fail_closed"] is True
        assert fixture["block_reasons"]

    rows = load_registry_records(Path.cwd() / "storage" / "registries" / "phase9_2_secret_manager_runtime_binding_registry.jsonl")
    assert rows
    latest = rows[-1]
    assert latest["secret_manager_runtime_binding_performed"] is False
    assert latest["phase9_2_order_submission_authorized"] is False
    assert latest["actual_order_submission_performed"] is False


def test_phase9_2_secret_manager_runtime_binding_template_preserves_source_lineage() -> None:
    endpoint_report = _latest_json("phase9_2_endpoint_time_risk_refresh_report.json")
    secret_report = _latest_json("phase8_1_secret_manager_key_handling_design_report.json")
    template = build_secret_manager_runtime_binding_template(endpoint_report, secret_report)

    assert template["source_endpoint_time_risk_refresh_id"] == endpoint_report["phase9_2_endpoint_time_risk_refresh_id"]
    assert template["source_endpoint_time_risk_refresh_hash"]
    assert template["source_secret_manager_design_hash"]
    assert template["secret_manager_runtime_binding_performed"] is False
    assert template["phase9_2_order_submission_authorized"] is False
