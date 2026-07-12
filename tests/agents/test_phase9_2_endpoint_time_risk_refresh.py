from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.phase9_2_endpoint_time_risk_refresh_design import (
    STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED,
    build_endpoint_time_risk_refresh_template,
    persist_phase9_2_endpoint_time_risk_refresh_report,
    validate_endpoint_time_risk_refresh_template,
)


def _latest_json(name: str) -> dict:
    path = Path.cwd() / "storage" / "latest" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase9_2_endpoint_time_risk_refresh_records_still_disabled_artifacts() -> None:
    report = persist_phase9_2_endpoint_time_risk_refresh_report(run_application_boundary_first=True)

    assert report["status"] == STATUS_PHASE9_2_ENDPOINT_TIME_RISK_REFRESH_RECORDED_STILL_DISABLED
    assert report["phase9_2_endpoint_time_risk_refresh_recorded"] is True
    assert report["endpoint_time_risk_refresh_design_ready"] is True
    assert report["endpoint_time_risk_refresh_performed"] is False
    assert report["endpoint_time_real_market_data_bound"] is False
    assert report["runtime_authority_granted"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["order_endpoint_called"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["block_reasons"]

    latest = Path.cwd() / "storage" / "latest"
    assert (latest / "phase9_2_endpoint_time_risk_refresh_report.json").exists()
    assert (latest / "endpoint_time_risk_refresh_DESIGN_STILL_DISABLED_REVIEW_ONLY.json").exists()
    assert (latest / "phase9_2_endpoint_time_risk_refresh_validation_report.json").exists()
    assert (latest / "phase9_2_endpoint_time_risk_refresh_negative_fixture_results.json").exists()


def test_phase9_2_endpoint_time_risk_refresh_template_validates_fresh_review_only_fixture() -> None:
    template = _latest_json("endpoint_time_risk_refresh_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    validation = validate_endpoint_time_risk_refresh_template(template)

    assert validation["phase9_2_endpoint_time_risk_refresh_template_valid"] is True
    assert validation["blocked"] is False
    assert validation["fail_closed"] is False
    assert validation["block_reasons"] == []


def test_phase9_2_endpoint_time_risk_refresh_blocks_stale_price() -> None:
    template = _latest_json("endpoint_time_risk_refresh_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    template["price_age_seconds"] = 60
    template["price_freshness_window_seconds"] = 5

    validation = validate_endpoint_time_risk_refresh_template(template)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert "PHASE9_2_ENDPOINT_TIME_REFRESH_PRICE_STALE_OR_OUTSIDE_WINDOW" in validation["block_reasons"]


def test_phase9_2_endpoint_time_risk_refresh_blocks_unsafe_submit_flags() -> None:
    template = _latest_json("endpoint_time_risk_refresh_DESIGN_STILL_DISABLED_REVIEW_ONLY.json")
    template["phase9_2_order_submission_authorized"] = True
    template["order_endpoint_called"] = True
    template["signature_created"] = True

    validation = validate_endpoint_time_risk_refresh_template(template)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    joined = "\n".join(validation["block_reasons"])
    assert "PHASE9_2_ENDPOINT_TIME_REFRESH_UNSAFE_FLAGS" in joined
    assert "phase9_2_order_submission_authorized" in joined
    assert "order_endpoint_called" in joined
    assert "signature_created" in joined


def test_phase9_2_endpoint_time_risk_refresh_negative_fixtures_and_registry() -> None:
    report = _latest_json("phase9_2_endpoint_time_risk_refresh_report.json")
    negative = report["negative_fixture_results"]

    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert len(negative["fixture_results"]) >= 20
    for fixture in negative["fixture_results"].values():
        assert fixture["blocked"] is True
        assert fixture["fail_closed"] is True
        assert fixture["block_reasons"]

    rows = load_registry_records(Path.cwd() / "storage" / "registries" / "phase9_2_endpoint_time_risk_refresh_registry.jsonl")
    assert rows
    latest = rows[-1]
    assert latest["runtime_authority_granted"] is False
    assert latest["phase9_2_order_submission_authorized"] is False
    assert latest["actual_order_submission_performed"] is False


def test_phase9_2_endpoint_time_risk_refresh_template_preserves_source_lineage() -> None:
    app_report = _latest_json("phase9_2_runtime_authority_application_boundary_report.json")
    risk_report = _latest_json("phase8_3_hot_path_preorder_risk_gate_report.json")
    template = build_endpoint_time_risk_refresh_template(app_report, risk_report)

    assert template["source_runtime_authority_application_boundary_id"] == app_report["phase9_2_runtime_authority_application_boundary_id"]
    assert template["source_runtime_authority_application_boundary_hash"]
    assert template["source_hot_path_risk_gate_hash"]
    assert template["endpoint_time_risk_refresh_performed"] is False
    assert template["phase9_2_order_submission_authorized"] is False
