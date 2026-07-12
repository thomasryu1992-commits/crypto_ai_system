from __future__ import annotations

import traceback

from config.settings import LATEST_DIR
from core.json_io import atomic_write_json
from core.time_utils import utc_now_iso


def _safe_permission_fix() -> None:
    try:
        from fix_storage_permissions import main as fix_storage_permissions
        fix_storage_permissions()
    except Exception:
        pass


def run_operational_dry_run() -> dict:
    _safe_permission_fix()
    try:
        from run_full_cycle import run_full_cycle
        result = run_full_cycle()
        out = {
            "created_at": utc_now_iso(),
            "status": "PASSED",
            "mode": "operational_dry_run_step150_stable",
            "final_decision": result.get("trade_decision", {}).get("final_decision"),
            "data_health": result.get("data_health", {}).get("status"),
            "order_status": result.get("order", {}).get("status"),
            "spreadsheet_status": result.get("spreadsheet", {}).get("status"),
            "outcome_status": result.get("outcome", {}).get("status"),
            "performance_report_status": result.get("performance_report", {}).get("status"),
            "candidate_profile_status": result.get("candidate_profile", {}).get("status"),
            "candidate_profile_creation_status": result.get("candidate_profile", {}).get("creation_status"),
            "prompt_profile_library_status": result.get("prompt_profile_library", {}).get("status"),
            "prompt_profile_library_registry_count": result.get("prompt_profile_library", {}).get("registry_record_count"),
            "approval_registry_status": result.get("approval_registry", {}).get("approval_registry_status"),
            "approval_validation_status": result.get("approval_registry", {}).get("validation_status"),
            "settings_write_preview_status": result.get("settings_write_preview", {}).get("status"),
            "settings_write_preview_guard_id": result.get("settings_write_preview", {}).get("settings_write_preview_guard_id"),
            "agent_library_contract_review_status": result.get("agent_library", {}).get("agent_library_contract_review", {}).get("status"),
            "agent_library_contract_review_id": result.get("agent_library", {}).get("agent_library_contract_review", {}).get("agent_library_contract_review_report_id"),
            "review_only_export_packet_status": result.get("review_only_export_packet", {}).get("status"),
            "review_only_export_packet_id": result.get("review_only_export_packet", {}).get("review_only_export_packet_id"),
            "real_testnet_read_only_adapter_ready": result.get("real_testnet_read_only_adapter", {}).get("adapter_ready_for_read_only_testnet_probe"),
            "real_testnet_read_only_adapter_evidence_id": result.get("real_testnet_read_only_adapter", {}).get("real_testnet_read_only_adapter_evidence_id"),
            "testnet_secret_metadata_intake_status": result.get("testnet_secret_metadata_intake", {}).get("validation_status"),
            "testnet_secret_metadata_intake_valid": result.get("testnet_secret_metadata_intake", {}).get("valid"),
            "testnet_secret_metadata_intake_id": result.get("testnet_secret_metadata_intake", {}).get("testnet_secret_metadata_intake_id"),
            "real_read_only_venue_probe_status": result.get("real_read_only_venue_probe", {}).get("status"),
            "real_read_only_venue_probe_valid": result.get("real_read_only_venue_probe", {}).get("valid"),
            "real_read_only_venue_probe_id": result.get("real_read_only_venue_probe", {}).get("real_read_only_venue_probe_id"),
            "signed_testnet_pre_submit_status": result.get("signed_testnet_pre_submit", {}).get("status"),
            "signed_testnet_pre_submit_valid": result.get("signed_testnet_pre_submit", {}).get("valid"),
            "signed_testnet_pre_submit_id": result.get("signed_testnet_pre_submit", {}).get("signed_testnet_pre_submit_validation_id"),
            "signed_testnet_execution_enablement_status": result.get("signed_testnet_execution_enablement", {}).get("status"),
            "signed_testnet_execution_enablement_valid": result.get("signed_testnet_execution_enablement", {}).get("valid"),
            "signed_testnet_execution_enablement_packet_id": result.get("signed_testnet_execution_enablement", {}).get("signed_testnet_execution_enablement_packet_id"),
            "signed_testnet_order_executor_status": result.get("signed_testnet_order_executor", {}).get("status"),
            "signed_testnet_order_execution_id": result.get("signed_testnet_order_executor", {}).get("signed_testnet_execution_id"),
            "signed_testnet_order_submitted_to_exchange": result.get("signed_testnet_order_executor", {}).get("submitted_to_exchange"),
            "signed_testnet_reconciliation_status": result.get("signed_testnet_reconciliation", {}).get("status"),
            "signed_testnet_reconciliation_id": result.get("signed_testnet_reconciliation", {}).get("signed_testnet_reconciliation_id"),
            "signed_testnet_reconciliation_promotion_blocker": result.get("signed_testnet_reconciliation", {}).get("promotion_blocker"),
            "signed_testnet_session_close_status": result.get("signed_testnet_session_close", {}).get("status"),
            "signed_testnet_session_close_id": result.get("signed_testnet_session_close", {}).get("signed_testnet_session_close_report_id"),
            "signed_testnet_session_close_promotion_recommendation": result.get("signed_testnet_session_close", {}).get("promotion_recommendation"),
            "live_read_only_adapter_probe_status": result.get("live_read_only_adapter_probe", {}).get("status"),
            "live_read_only_adapter_probe_valid": result.get("live_read_only_adapter_probe", {}).get("valid"),
            "live_read_only_adapter_probe_id": result.get("live_read_only_adapter_probe", {}).get("live_read_only_adapter_probe_id"),
            "live_read_only_adapter_probe_live_canary_ready": result.get("live_read_only_adapter_probe", {}).get("live_canary_ready"),
            "live_key_scope_validation_status": result.get("live_key_scope_validation", {}).get("status"),
            "live_key_scope_validation_valid": result.get("live_key_scope_validation", {}).get("valid"),
            "live_key_scope_validation_id": result.get("live_key_scope_validation", {}).get("live_key_scope_validation_id"),
            "live_key_scope_validation_live_canary_ready": result.get("live_key_scope_validation", {}).get("live_canary_ready"),
            "live_canary_approval_packet_status": result.get("live_canary_approval_packet", {}).get("status"),
            "live_canary_approval_packet_valid": result.get("live_canary_approval_packet", {}).get("valid"),
            "live_canary_approval_packet_id": result.get("live_canary_approval_packet", {}).get("live_canary_approval_packet_id"),
            "live_canary_approval_review_ready": result.get("live_canary_approval_packet", {}).get("live_canary_approval_review_ready"),
            "live_canary_execution_enabled": result.get("live_canary_approval_packet", {}).get("live_canary_execution_enabled"),

            "live_canary_order_executor_status": result.get("live_canary_order_executor", {}).get("status"),
            "live_canary_execution_id": result.get("live_canary_order_executor", {}).get("live_canary_execution_id"),
            "live_canary_submitted_to_exchange": result.get("live_canary_order_executor", {}).get("submitted_to_exchange"),
            "live_canary_actual_submission_performed": result.get("live_canary_order_executor", {}).get("actual_submission_performed"),
            "live_canary_reconciliation_status": result.get("live_canary_reconciliation", {}).get("status"),
            "live_canary_reconciliation_id": result.get("live_canary_reconciliation", {}).get("live_canary_reconciliation_id"),
            "live_canary_reconciliation_promotion_blocker": result.get("live_canary_reconciliation", {}).get("promotion_blocker"),
            "monitoring_alerting_status": result.get("monitoring_alerting", {}).get("status"),
            "monitoring_alerting_id": result.get("monitoring_alerting", {}).get("monitoring_alerting_report_id"),
            "monitoring_alerting_alert_count": result.get("monitoring_alerting", {}).get("alert_count"),
            "monitoring_alerting_critical_alert_count": result.get("monitoring_alerting", {}).get("critical_alert_count"),
            "monitoring_alerting_telegram_message_sent": result.get("monitoring_alerting", {}).get("telegram_message_sent"),
            "monitoring_alerting_external_notification_sent": result.get("monitoring_alerting", {}).get("external_notification_sent"),
            "deployment_runbook_status": result.get("deployment_runbook", {}).get("status"),
            "deployment_runbook_id": result.get("deployment_runbook", {}).get("deployment_runbook_id"),
            "deployment_runbook_deployment_ready": result.get("deployment_runbook", {}).get("deployment_ready"),
            "deployment_runbook_server_deployment_performed": result.get("deployment_runbook", {}).get("server_deployment_performed"),
            "canary_outcome_report_status": result.get("canary_outcome_report", {}).get("status"),
            "canary_outcome_report_id": result.get("canary_outcome_report", {}).get("canary_outcome_report_id"),
            "canary_outcome_report_recommendation": result.get("canary_outcome_report", {}).get("live_scaled_readiness_recommendation"),
            "canary_outcome_report_live_scaled_promotion_allowed": result.get("canary_outcome_report", {}).get("live_scaled_promotion_allowed_by_this_module"),
            "live_scaled_readiness_gate_status": result.get("live_scaled_readiness_gate", {}).get("status"),
            "live_scaled_readiness_gate_id": result.get("live_scaled_readiness_gate", {}).get("live_scaled_readiness_gate_id"),
            "live_scaled_readiness_gate_decision": result.get("live_scaled_readiness_gate", {}).get("gate_decision"),
            "live_scaled_readiness_gate_promotion_allowed": result.get("live_scaled_readiness_gate", {}).get("live_scaled_promotion_allowed_by_this_module"),
        }
        atomic_write_json(LATEST_DIR / "operational_dry_run_result.json", out)
        print("Operational dry run Step150: PASSED")
        return out
    except Exception as exc:
        out = {
            "created_at": utc_now_iso(),
            "status": "FAILED",
            "mode": "operational_dry_run_step150_stable",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-12:],
        }
        atomic_write_json(LATEST_DIR / "operational_dry_run_result.json", out)
        print("Operational dry run Step150: FAILED")
        print(f"{exc.__class__.__name__}: {exc}")
        print("Detail saved to storage/latest/operational_dry_run_result.json")
        return out


def main() -> None:
    run_operational_dry_run()


if __name__ == "__main__":
    main()
