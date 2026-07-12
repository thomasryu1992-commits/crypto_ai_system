from __future__ import annotations

import json
import shutil
from pathlib import Path

from crypto_ai_system.validation.phase9_2_closure_packet import build_phase9_2_closure_packet, persist_phase9_2_closure_packet
from crypto_ai_system.validation.phase9_3_status_polling_cancel_boundary import build_phase9_3_status_polling_cancel_boundary, persist_phase9_3_status_polling_cancel_boundary


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_ready_reports(root: Path) -> None:
    latest = root / "storage" / "latest"
    _write(latest / "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json", {
        "status": "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VALIDATED_REVIEW_ONLY_NO_ORDER_SUBMIT",
        "blocked": False,
        "fail_closed": False,
        "operator_filled_approval_validated": True,
        "ready_for_one_order_runtime_submit_operator_review_only": True,
        "public_metadata_conditions_ready_for_submit_review_only": True,
        "real_testnet_submit_may_begin": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "signature_created": False,
        "signed_request_created": False,
    })
    _write(latest / "phase9_2_quick_one_order_approval_ready_check_report.json", {
        "status": "PHASE9_2_SEPARATE_ONE_ORDER_RUNTIME_SUBMIT_APPROVAL_PACKET_VALIDATED_REVIEW_ONLY_NO_ORDER_SUBMIT",
        "blocked": False,
        "fail_closed": False,
        "operator_filled_approval_validated": True,
        "ready_for_one_order_runtime_submit_operator_review_only": True,
        "public_metadata_conditions_ready_for_submit_review_only": True,
        "real_testnet_submit_may_begin": False,
    })
    _write(latest / "phase9_2_final_pre_submit_checklist_report.json", {
        "status": "PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_READY_FOR_SEPARATE_ONE_ORDER_APPROVAL_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "ready_for_separate_one_order_runtime_approval_review_only": True,
        "real_testnet_submit_may_begin": False,
    })
    _write(latest / "phase9_2_public_metadata_probe_bridge_report.json", {
        "status": "PHASE9_2_PUBLIC_METADATA_PROBE_BRIDGE_VALIDATED_PUBLIC_METADATA_ONLY_NO_ORDER_SUBMIT",
        "blocked": False,
        "fail_closed": False,
        "public_metadata_conditions_ready_for_submit_review_only": True,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": True,
        "real_testnet_submit_may_begin": False,
    })
    _write(latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json", {
        "status": "PHASE9_2_PUBLIC_METADATA_PROBE_RESULT_FILLED_VALIDATION_VALIDATED_NO_ORDER_SUBMIT_REVIEW_ONLY",
        "blocked": False,
        "fail_closed": False,
        "operator_filled_public_metadata_probe_result_validated": True,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": True,
        "real_testnet_submit_may_begin": False,
    })


def test_phase9_2_closure_packet_ready_when_review_evidence_valid(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _seed_ready_reports(root)
    report = build_phase9_2_closure_packet(root)
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase9_2_closed_review_only"] is True
    assert report["ready_for_phase9_3_boundary_review_only"] is True
    assert report["real_testnet_submit_may_begin"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False


def test_phase9_2_closure_blocks_if_order_flag_true(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _seed_ready_reports(root)
    path = root / "storage" / "latest" / "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["order_endpoint_called"] = True
    _write(path, data)
    report = build_phase9_2_closure_packet(root)
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert any("UNSAFE_TRUE_FLAGS" in reason for reason in report["block_reasons"])


def test_phase9_3_boundary_ready_but_no_endpoints_when_closure_ready(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _seed_ready_reports(root)
    persist_phase9_2_closure_packet(root)
    report = build_phase9_3_status_polling_cancel_boundary(root, run_closure_first=False)
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only"] is True
    assert report["real_phase9_3_status_polling_may_begin"] is False
    assert report["order_status_endpoint_called"] is False
    assert report["cancel_endpoint_called"] is False
    assert report["signature_created"] is False


def test_phase9_3_boundary_blocks_without_closure(tmp_path: Path) -> None:
    report = build_phase9_3_status_polling_cancel_boundary(tmp_path / "proj", run_closure_first=False)
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only"] is False
    assert report["order_status_endpoint_called"] is False
    assert report["cancel_endpoint_called"] is False


def test_persist_writes_closure_and_boundary_reports(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _seed_ready_reports(root)
    closure = persist_phase9_2_closure_packet(root)
    boundary = persist_phase9_3_status_polling_cancel_boundary(root, run_closure_first=False)
    assert (root / "storage" / "latest" / "phase9_2_closure_packet_report.json").exists()
    assert (root / "storage" / "latest" / "phase9_3_status_polling_cancel_boundary_report.json").exists()
    assert closure["phase9_2_closed_review_only"] is True
    assert boundary["phase9_3_boundary_ready_for_post_submit_order_id_intake_review_only"] is True
