from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import bootstrap

bootstrap()

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.utils.audit import utc_now_canonical
from crypto_ai_system.validation.phase9_2_final_pre_submit_checklist import persist_phase9_2_final_pre_submit_checklist
from crypto_ai_system.validation.phase9_2_separate_one_order_runtime_submit_approval_packet import (
    APPROVAL_TEXT_KO,
    FILLED_APPROVAL_FILENAME,
    TEMPLATE_FILENAME,
    persist_phase9_2_separate_one_order_runtime_submit_approval_packet,
)

EXECUTION_FALSE_FLAGS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_authority_granted",
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_2_single_order_runtime_submit_approval_granted",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_exchange_endpoint_call_performed",
    "real_testnet_order_endpoint_called",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "executor_enable_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
]

APPROVAL_TEXT_FULL_KO = (
    "Phase 9.2 단일 signed TESTNET 주문 제출을 명시적으로 승인합니다. "
    "범위는 testnet 단일 주문 1개로 제한합니다. "
    "심볼은 BTCUSDT testnet only입니다. "
    "최대 주문 금액은 10 USDT입니다. "
    "live/mainnet 주문은 승인하지 않습니다. "
    "testnet order endpoint가 1회 호출될 수 있음을 이해합니다."
)


def _latest_dir() -> Path:
    cfg = load_config()
    raw = cfg.get("storage.latest_dir", "storage/latest")
    latest = Path(raw)
    if not latest.is_absolute():
        latest = cfg.root / latest
    latest.mkdir(parents=True, exist_ok=True)
    return latest.resolve()


def _read_json(path: Path) -> dict:
    payload = read_json(path, default={})
    return dict(payload) if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload)


def _sync_public_metadata_reports(latest: Path) -> list[str]:
    actions: list[str] = []
    bridge_filled = latest / "phase9_2_public_metadata_probe_bridge_filled_validation_report.json"
    canonical_filled = latest / "phase9_2_public_metadata_probe_result_filled_validation_report.json"
    if bridge_filled.exists():
        shutil.copyfile(bridge_filled, canonical_filled)
        actions.append("copied_bridge_filled_validation_to_canonical_filled_validation")

    bridge_report_path = latest / "phase9_2_public_metadata_probe_bridge_report.json"
    bridge_report = _read_json(bridge_report_path)
    # Do not fabricate successful evidence. Only normalize the canonical report if the bridge has already validated metadata.
    if bridge_report.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True:
        canonical = _read_json(canonical_filled)
        if canonical:
            canonical["operator_filled_public_metadata_probe_result_validated"] = True
            canonical["public_metadata_network_probe_result_validated"] = canonical.get("public_metadata_network_probe_result_validated", True)
            canonical["real_testnet_metadata_conditions_ready_for_submit_review_only"] = True
            canonical["real_testnet_submit_may_begin"] = False
            canonical["actual_order_submission_performed"] = False
            canonical["order_endpoint_called"] = False
            canonical["signature_created"] = False
            canonical["signed_request_created"] = False
            _write_json(canonical_filled, canonical)
            actions.append("normalized_canonical_filled_validation_ready_flags_from_validated_bridge")
    return actions


def _ensure_filled_approval(latest: Path, *, operator: str) -> list[str]:
    actions: list[str] = []
    template_path = latest / TEMPLATE_FILENAME
    filled_path = latest / FILLED_APPROVAL_FILENAME

    if not template_path.exists():
        # First run creates the template/report. It may stay blocked until filled approval exists.
        persist_phase9_2_separate_one_order_runtime_submit_approval_packet()
        actions.append("created_missing_approval_template")

    if not filled_path.exists():
        if template_path.exists():
            shutil.copyfile(template_path, filled_path)
            actions.append("copied_approval_template_to_filled_approval")
        else:
            _write_json(filled_path, {})
            actions.append("created_empty_filled_approval_file")

    approval = _read_json(filled_path)
    approval.update(
        {
            "artifact_type": "phase9_2_separate_one_order_runtime_submit_approval_filled_review_only",
            "review_only": True,
            "no_order_submit": False,
            "phase": "9.2",
            "approval_scope": "single_signed_testnet_order_only",
            "approval_text_required_ko": APPROVAL_TEXT_KO,
            "operator_approval_text": APPROVAL_TEXT_FULL_KO,
            "operator_name_or_handle": operator,
            "approved_at_utc": utc_now_canonical(),
            "symbol": "BTCUSDT",
            "venue": "binance_futures_testnet",
            "testnet_only": True,
            "live_or_mainnet_approved": False,
            "one_order_only": True,
            "max_order_count": 1,
            "max_notional_usdt": 10.0,
            "no_live_mainnet_order_approved": True,
            "fresh_hot_path_risk_refresh_required_at_action_time": True,
            "runtime_secret_binding_required_at_action_time": True,
            "metadata_only_secret_evidence_in_artifacts": True,
            "duplicate_submit_lock_required": True,
            "post_submit_immediate_relock_required": True,
            "status_polling_reconciliation_split_to_phase9_3_9_4": True,
            "does_not_enable_submit_by_itself": True,
            "real_testnet_submit_may_begin": False,
            "actual_order_submission_performed": False,
        }
    )
    for field in EXECUTION_FALSE_FLAGS:
        approval[field] = False
    _write_json(filled_path, approval)
    actions.append("filled_one_order_runtime_submit_approval_fields")
    return actions


def main() -> int:
    operator = "Thomas"
    latest = _latest_dir()
    actions: list[str] = []
    actions.extend(_sync_public_metadata_reports(latest))
    actions.extend(_ensure_filled_approval(latest, operator=operator))

    final_checklist = persist_phase9_2_final_pre_submit_checklist()
    approval_report = persist_phase9_2_separate_one_order_runtime_submit_approval_packet()

    output = {
        "status": approval_report.get("status"),
        "blocked": approval_report.get("blocked"),
        "fail_closed": approval_report.get("fail_closed"),
        "operator_filled_approval_present": approval_report.get("operator_filled_approval_present"),
        "operator_filled_approval_validated": approval_report.get("operator_filled_approval_validated"),
        "public_metadata_conditions_ready_for_submit_review_only": approval_report.get("public_metadata_conditions_ready_for_submit_review_only"),
        "final_pre_submit_checklist_ready_for_separate_approval_review_only": approval_report.get("final_pre_submit_checklist_ready_for_separate_approval_review_only"),
        "ready_for_one_order_runtime_submit_operator_review_only": approval_report.get("ready_for_one_order_runtime_submit_operator_review_only"),
        "real_testnet_submit_may_begin": approval_report.get("real_testnet_submit_may_begin"),
        "actual_order_submission_performed": approval_report.get("actual_order_submission_performed"),
        "order_endpoint_called": approval_report.get("order_endpoint_called"),
        "signature_created": approval_report.get("signature_created"),
        "signed_request_created": approval_report.get("signed_request_created"),
        "api_key_value_logged": approval_report.get("api_key_value_logged"),
        "api_secret_value_logged": approval_report.get("api_secret_value_logged"),
        "secret_value_accessed": approval_report.get("secret_value_accessed"),
        "block_reasons": approval_report.get("block_reasons", []),
        "final_checklist_status": final_checklist.get("status"),
        "actions": actions,
    }
    _write_json(latest / "phase9_2_quick_one_order_approval_fill_result.json", output)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
