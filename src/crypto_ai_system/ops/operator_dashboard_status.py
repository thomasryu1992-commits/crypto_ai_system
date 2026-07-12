from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from crypto_ai_system.execution.runtime_disabled_flags import (
    EXECUTION_FLAGS,
    PHASE_STATUS_MARKERS,
)

FORBIDDEN_UI_ACTIONS = [
    "submit_order",
    "place_order",
    "cancel_order",
    "enable_testnet",
    "enable_live",
    "enable_executor",
    "change_settings",
    "enter_api_secret",
    "enter_private_key",
]

SAFE_REVIEW_ONLY_SCRIPTS = {
    "Phase 9.2 final approval package": "scripts/build_phase9_2_final_approval_package_minimal.py",
    "Phase 9.2 manual final confirmation": "scripts/build_phase9_2_manual_final_confirmation.py",
    "Phase 9.2 runtime submit boundary": "scripts/build_phase9_2_runtime_submit_action_boundary.py",
    "Phase 9.3/9.4 blocked design": "scripts/build_phase9_3_9_4_blocked_design_hardening.py",
    "Phase 10 blocked session validation design": "scripts/build_phase10_signed_testnet_session_validation_blocked_design.py",
    "Phase 11 live canary preparation blocked design": "scripts/build_phase11_live_canary_preparation_blocked_design.py",
    "Phase 9-10 signed testnet evidence intake": "scripts/build_phase9_10_signed_testnet_evidence_intake.py",
    "Phase 9.2 mock submit evidence flow": "scripts/build_phase9_2_mock_submit_evidence_flow.py",
    "Phase 9.2 real testnet endpoint adapter preflight": "scripts/build_phase9_2_real_testnet_endpoint_adapter_preflight.py",
    "Phase 9.2 real testnet network dry probe": "scripts/build_phase9_2_real_testnet_network_dry_probe.py",
    "Phase 9.2 public metadata network dry probe result intake": "scripts/build_phase9_2_public_metadata_network_dry_probe_result_intake.py",
    "Phase 9.2 public metadata probe result filled validation": "scripts/build_phase9_2_public_metadata_probe_result_filled_validation.py",
    "Phase 9.2 real public metadata probe command": "scripts/run_phase9_2_real_public_metadata_probe_command.py",
    "Phase 9.2 public metadata probe bridge": "scripts/run_phase9_2_public_metadata_probe_bridge.py",
    "Phase 9.2 final pre-submit checklist": "scripts/build_phase9_2_final_pre_submit_checklist.py",
    "Phase 9.2 separate one-order runtime submit approval packet": "scripts/build_phase9_2_separate_one_order_runtime_submit_approval_packet.py",
    "Phase 9.2 closure packet": "scripts/build_phase9_2_closure_packet.py",
    "Phase 9.3 status polling cancel boundary": "scripts/build_phase9_3_status_polling_cancel_boundary.py",
    "Phase 9.2 close and Phase 9.3 boundary quick check": "scripts/quick_phase9_2_close_and_phase9_3_boundary.py",
    "Operator dashboard status": "scripts/build_operator_dashboard_status.py",
}

REPORT_PATTERNS = {
    "system_status": [
        "phase9_3_status_polling_cancel_boundary_report.json",
        "phase9_2_closure_packet_report.json",
        "phase9_2_quick_one_order_approval_ready_check_report.json",
        "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json",
        "phase9_2_final_pre_submit_checklist_report.json",
        "phase9_2_public_metadata_probe_bridge_report.json",
        "phase9_2_real_public_metadata_probe_command_report.json",
        "phase9_2_public_metadata_probe_result_filled_validation_report.json",
        "phase9_2_public_metadata_network_dry_probe_result_intake_report.json",
        "phase9_2_real_testnet_network_dry_probe_report.json",
        "phase9_2_real_testnet_endpoint_adapter_preflight_report.json",
        "phase9_2_mock_submit_evidence_flow_report.json",
        "phase9_10_signed_testnet_evidence_intake_report.json",
        "phase11_live_canary_preparation_blocked_design_report.json",
        "phase10_signed_testnet_session_validation_blocked_design_report.json",
        "phase9_2_runtime_submit_action_boundary_report.json",
        "phase9_2_manual_final_confirmation_report.json",
        "phase9_2_final_approval_package_report.json",
    ],
    "data_health": ["data_health_report.json", "data_snapshot_manifest.json", "feature_store_manifest.json"],
    "research_signal": ["research_signal_debug.json", "research_signal_registry_record.json", "signal_qa_report.json"],
    "risk_gate": [
        "phase8_3_hot_path_preorder_risk_gate_report.json",
        "phase8_3_hot_path_preorder_risk_gate_guard_report.json",
        "risk_gate_report.json",
    ],
    "approval_blockers": [
        "phase9_3_status_polling_cancel_boundary_report.json",
        "phase9_2_closure_packet_report.json",
        "phase9_2_quick_one_order_approval_ready_check_report.json",
        "phase9_2_separate_one_order_runtime_submit_approval_packet_report.json",
        "phase9_2_final_pre_submit_checklist_report.json",
        "phase9_2_public_metadata_probe_bridge_report.json",
        "phase9_2_real_public_metadata_probe_command_report.json",
        "phase9_2_public_metadata_probe_result_filled_validation_report.json",
        "phase9_2_public_metadata_network_dry_probe_result_intake_report.json",
        "phase9_2_real_testnet_network_dry_probe_report.json",
        "phase9_2_real_testnet_endpoint_adapter_preflight_report.json",
        "phase9_2_mock_submit_evidence_flow_report.json",
        "phase9_10_signed_testnet_evidence_intake_report.json",
        "phase11_live_canary_preparation_blocked_design_report.json",
        "phase9_2_submit_guard_recheck_after_operator_fixture_report.json",
        "phase9_2_runtime_submit_action_boundary_report.json",
        "phase10_signed_testnet_session_validation_blocked_design_report.json",
        "phase9_3_9_4_blocked_design_hardening_report.json",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else {"value": data}


def report_ref(path: Path) -> Dict[str, Any]:
    data = read_json(path)
    stat = path.stat()
    result: Dict[str, Any] = {
        "name": path.name,
        "path": str(path.as_posix()),
        "exists": True,
        "size_bytes": stat.st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if data is not None:
        result.update(
            {
                "status": data.get("status"),
                "blocked": data.get("blocked"),
                "fail_closed": data.get("fail_closed"),
                "review_only": data.get("review_only"),
                "created_at_utc": data.get("created_at_utc"),
            }
        )
    return result


def find_first_json(latest_dir: Path, names: Iterable[str]) -> Optional[Path]:
    for name in names:
        p = latest_dir / name
        if p.exists():
            return p
    return None


def collect_reports(latest_dir: Path) -> Dict[str, Any]:
    reports: Dict[str, Any] = {}
    for section, names in REPORT_PATTERNS.items():
        primary = find_first_json(latest_dir, names)
        reports[section] = report_ref(primary) if primary else {"exists": False, "searched": list(names)}
    recent_json = sorted(latest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:25]
    recent_md = sorted(latest_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    reports["recent_json_reports"] = [report_ref(p) for p in recent_json]
    reports["recent_markdown_reports"] = [
        {"name": p.name, "path": str(p.as_posix()), "exists": True, "size_bytes": p.stat().st_size}
        for p in recent_md
    ]
    return reports


def extract_flags_from_reports(latest_dir: Path) -> Dict[str, bool]:
    observed: Dict[str, bool] = {flag: False for flag in EXECUTION_FLAGS}
    for path in latest_dir.glob("*.json"):
        data = read_json(path)
        if not data:
            continue
        for flag in EXECUTION_FLAGS:
            value = data.get(flag)
            if value is True:
                observed[flag] = True
            elif value is False and flag not in observed:
                observed[flag] = False
        nested = data.get("negative_fixture_results")
        if isinstance(nested, Mapping):
            for flag in EXECUTION_FLAGS:
                if nested.get(flag) is True:
                    observed[flag] = True
    return observed


def collect_blockers(latest_dir: Path) -> List[str]:
    blockers: List[str] = []
    keys = [
        "block_reasons",
        "remaining_real_submit_blockers",
        "remaining_runtime_authority_blockers",
        "remaining_application_blockers",
        "remaining_real_submit_blockers",
        "missing_required_evidence",
        "required_evidence_not_ready",
    ]
    for path in latest_dir.glob("*.json"):
        data = read_json(path)
        if not data:
            continue
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item not in blockers:
                        blockers.append(item)
        if data.get("blocked") is True and isinstance(data.get("status"), str):
            status = data["status"]
            if status not in blockers:
                blockers.append(status)
    return blockers[:50]


def summarize_data_health(latest_dir: Path) -> Dict[str, Any]:
    data = read_json(latest_dir / "data_health_report.json") or {}
    manifest = read_json(latest_dir / "data_snapshot_manifest.json") or {}
    return {
        "report_present": bool(data),
        "data_quality_status": data.get("data_quality_status") or manifest.get("data_quality_status"),
        "hard_required_sources_present": data.get("hard_required_sources_present") or manifest.get("hard_required_sources_present"),
        "optional_sources_missing": data.get("optional_sources_missing") or manifest.get("optional_sources_missing"),
        "fallback_flag": bool(data.get("fallback_flag") or manifest.get("fallback_flag")),
        "synthetic_flag": bool(data.get("synthetic_flag") or manifest.get("synthetic_flag")),
        "sample_flag": bool(data.get("sample_flag") or manifest.get("sample_flag")),
        "stale_source_count": data.get("stale_source_count") or manifest.get("stale_source_count"),
    }


def summarize_research_signal(latest_dir: Path) -> Dict[str, Any]:
    data = read_json(latest_dir / "research_signal_debug.json") or read_json(latest_dir / "research_signal_registry_record.json") or {}
    return {
        "report_present": bool(data),
        "research_signal_id": data.get("research_signal_id"),
        "signal_version": data.get("signal_version"),
        "profile_id": data.get("profile_id"),
        "permission_result": data.get("permission_result"),
        "final_signal_direction": data.get("final_signal_direction"),
        "live_candidate_eligible": data.get("live_candidate_eligible", False),
        "neutral_due_to_missing": data.get("neutral_due_to_missing"),
        "blocked_reason": data.get("blocked_reason"),
    }


def summarize_risk_gate(latest_dir: Path) -> Dict[str, Any]:
    data = (
        read_json(latest_dir / "phase8_3_hot_path_preorder_risk_gate_report.json")
        or read_json(latest_dir / "phase8_3_hot_path_preorder_risk_gate_guard_report.json")
        or read_json(latest_dir / "risk_gate_report.json")
        or {}
    )
    return {
        "report_present": bool(data),
        "status": data.get("status"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "hot_path_risk_gate_ready": data.get("phase8_3_hot_path_risk_gate_ready"),
        "guard_passed": data.get("hot_path_preorder_risk_gate_guard_passed"),
        "block_reasons": data.get("block_reasons", []),
    }


def build_operator_dashboard_status(root: Path | str = Path(".")) -> Dict[str, Any]:
    root = Path(root).resolve()
    latest_dir = root / "storage" / "latest"
    reports = collect_reports(latest_dir)
    flags = extract_flags_from_reports(latest_dir)
    unsafe_true_flags = sorted([k for k, v in flags.items() if v is True])
    blockers = collect_blockers(latest_dir)
    safe_next_actions = [
        "Review latest Phase 9.2 manual final confirmation and runtime submit boundary reports.",
        "Review Phase 9.3/9.4 blocked design reports before any real testnet order attempt.",
        "Generate review-only reports from the allowlisted buttons only.",
        "Keep real submit blocked until a separate explicit runtime-submit approval process is completed.",
        "Keep Phase 11 live canary preparation blocked until Phase 10 has multiple clean signed testnet sessions.",
    ]
    status = {
        "artifact_type": "operator_dashboard_status",
        "status_version": "operator_dashboard_status_v1",
        "created_at_utc": utc_now(),
        "project_stage": "review_only / signed-testnet-preparation / blocked-design",
        "frontend_authority": "read_only_report_viewer",
        "review_only": True,
        "runtime_mutation_allowed": False,
        "order_submission_allowed": False,
        "secret_input_allowed": False,
        "settings_edit_allowed": False,
        "executor_enable_allowed": False,
        "unsafe_true_execution_flags": unsafe_true_flags,
        "execution_flags_all_disabled": len(unsafe_true_flags) == 0,
        "execution_flags": flags,
        "central_execution_flag_source": "crypto_ai_system.execution.runtime_disabled_flags.EXECUTION_FLAGS",
        "phase_status_markers": dict(PHASE_STATUS_MARKERS),
        "data_health": summarize_data_health(latest_dir),
        "research_signal": summarize_research_signal(latest_dir),
        "risk_gate": summarize_risk_gate(latest_dir),
        "approval_and_blockers": {
            "remaining_blockers": blockers,
            "blocker_count": len(blockers),
            "order_submission_authorized": False,
            "actual_order_submission_performed": False,
        },
        "reports": reports,
        "disabled_controls": {
            action: {"enabled": False, "reason": "Forbidden in review-only operator console"}
            for action in FORBIDDEN_UI_ACTIONS
        },
        "review_only_script_allowlist": SAFE_REVIEW_ONLY_SCRIPTS,
        "safe_next_actions": safe_next_actions,
    }
    canonical = json.dumps(status, ensure_ascii=False, sort_keys=True)
    status["operator_dashboard_status_sha256"] = sha256_text(canonical)
    return status


def persist_operator_dashboard_status(root: Path | str = Path(".")) -> Dict[str, Any]:
    root = Path(root).resolve()
    latest_dir = root / "storage" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    status = build_operator_dashboard_status(root)
    out = latest_dir / "operator_dashboard_status.json"
    out.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    handoff = latest_dir / "OPERATOR_DASHBOARD_STATUS_HANDOFF_REVIEW_ONLY.md"
    handoff.write_text(
        "# Operator Dashboard Status / Review Only\n\n"
        "The operator console is a read-only report viewer. It does not grant trading permission, "
        "does not collect secrets, does not mutate settings, and does not enable executors.\n\n"
        f"- status: {status['project_stage']}\n"
        f"- execution_flags_all_disabled: {status['execution_flags_all_disabled']}\n"
        f"- unsafe_true_execution_flags: {status['unsafe_true_execution_flags']}\n"
        f"- blocker_count: {status['approval_and_blockers']['blocker_count']}\n"
        f"- phase9_2: {status['phase_status_markers']['phase9_2']}\n"
        f"- phase9_3: {status['phase_status_markers']['phase9_3']}\n"
        f"- phase10: {status['phase_status_markers']['phase10']}\n"
        f"- phase11: {status['phase_status_markers']['phase11']}\n",
        encoding="utf-8",
    )
    return status


if __name__ == "__main__":
    print(json.dumps(persist_operator_dashboard_status(Path.cwd()), ensure_ascii=False, indent=2))
