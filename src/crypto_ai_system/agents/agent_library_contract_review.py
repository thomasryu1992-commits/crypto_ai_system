from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.agents.contract_loader import (
    PROHIBITED_RUNTIME_PHRASES,
    load_agent_contracts,
    load_permission_policy_files,
    validate_permission_policies,
)
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

AGENT_LIBRARY_CONTRACT_REVIEW_VERSION = "step325_agent_library_contract_review_v1"
AGENT_LIBRARY_CONTRACT_REVIEW_REGISTRY_NAME = "agent_library_contract_review_registry"

STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED = "AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED"
STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_BLOCKED = "AGENT_LIBRARY_CONTRACT_REVIEW_BLOCKED"

AGENT_PERMISSION_POLICY_REPORT_VERSION = "step325_agent_permission_policy_report_v1"
AGENT_PROHIBITED_ACTION_SCAN_VERSION = "step325_agent_prohibited_action_scan_v1"

REQUIRED_LATEST_EVIDENCE_FILES: tuple[str, ...] = (
    "agent_lint_report.json",
    "agent_contract_validation_report.json",
    "agent_contract_index.json",
    "agent_contract_registry_record.json",
    "agent_output_schema_validation_report.json",
    "agent_eval_report.json",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_latest_json(latest: Path, name: str) -> dict[str, Any]:
    return _as_mapping(read_json(latest / name, default={}))


def _file_hashes(latest: Path, names: tuple[str, ...]) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    for name in names:
        path = latest / name
        if not path.exists():
            hashes[name] = None
            continue
        try:
            from crypto_ai_system.utils.audit import sha256_file

            hashes[name] = sha256_file(path)
        except Exception:
            hashes[name] = None
    return hashes


def build_agent_permission_policy_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    root = Path(project_root or cfg.root).resolve()
    policies = load_permission_policy_files(root)
    errors = validate_permission_policies(root)
    required_policy_names = ["read_only", "paper_only", "approval_required", "prohibited_actions"]
    policy_records: dict[str, Any] = {}
    for name, payload in sorted(policies.items()):
        policy_records[name] = {
            "policy_name": name,
            "keys": sorted(payload.keys()),
            "sha256": sha256_json(payload),
        }
    missing = [name for name in required_policy_names if name not in policies]
    report = {
        "agent_permission_policy_report_version": AGENT_PERMISSION_POLICY_REPORT_VERSION,
        "agent_permission_policy_report_id": stable_id(
            "agent_permission_policy_report", {"policies": policy_records, "errors": errors}, 24
        ),
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_PERMISSION_POLICY_REVIEW_RECORDED" if not errors and not missing else "AGENT_PERMISSION_POLICY_REVIEW_BLOCKED",
        "passed": not errors and not missing,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "required_policy_names": required_policy_names,
        "missing_policy_names": missing,
        "policy_count": len(policies),
        "policies": policy_records,
        "errors": errors,
    }
    report["agent_permission_policy_report_sha256"] = sha256_json(report)
    return report


def build_agent_prohibited_action_scan(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    root = Path(project_root or cfg.root).resolve()
    findings: list[dict[str, Any]] = []
    strict_flag_phrases = [phrase for phrase in PROHIBITED_RUNTIME_PHRASES if phrase.endswith("=true") or phrase.endswith(": true")]
    for contract in load_agent_contracts(root):
        lower_text = contract.raw_text.lower()
        found = [phrase for phrase in strict_flag_phrases if phrase in lower_text]
        if contract.frontmatter.get("can_modify_runtime") is not False:
            found.append("frontmatter_can_modify_runtime_not_false")
        if contract.frontmatter.get("can_submit_orders") is not False:
            found.append("frontmatter_can_submit_orders_not_false")
        findings.append(
            {
                "agent_id": contract.agent_id,
                "contract_path": contract.relative_path,
                "prohibited_findings": sorted(set(found)),
                "passed": not found,
            }
        )
    unsafe = [item for item in findings if not item.get("passed")]
    report = {
        "agent_prohibited_action_scan_version": AGENT_PROHIBITED_ACTION_SCAN_VERSION,
        "agent_prohibited_action_scan_id": stable_id("agent_prohibited_action_scan", {"findings": findings}, 24),
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_PROHIBITED_ACTION_SCAN_PASSED" if not unsafe and findings else "AGENT_PROHIBITED_ACTION_SCAN_BLOCKED",
        "passed": not unsafe and bool(findings),
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "agent_count": len(findings),
        "unsafe_agent_count": len(unsafe),
        "findings": findings,
    }
    report["agent_prohibited_action_scan_sha256"] = sha256_json(report)
    return report


def build_agent_library_contract_review_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    evidence = {name: _read_latest_json(latest, name) for name in REQUIRED_LATEST_EVIDENCE_FILES}
    missing = [name for name, payload in evidence.items() if not payload]

    lint_report = evidence["agent_lint_report.json"]
    contract_validation = evidence["agent_contract_validation_report.json"]
    contract_index = evidence["agent_contract_index.json"]
    contract_registry = evidence["agent_contract_registry_record.json"]
    output_schema_validation = evidence["agent_output_schema_validation_report.json"]
    eval_report = evidence["agent_eval_report.json"]

    permission_policy_report = build_agent_permission_policy_report(cfg=cfg, project_root=project_root or cfg.root)
    prohibited_action_scan = build_agent_prohibited_action_scan(cfg=cfg, project_root=project_root or cfg.root)

    block_reasons: list[str] = []
    for name in missing:
        block_reasons.append(f"missing_agent_library_evidence:{name}")

    checks = {
        "lint_passed": lint_report.get("passed") is True,
        "contract_validation_passed": contract_validation.get("passed") is True,
        "contract_index_recorded": contract_index.get("status") == "AGENT_CONTRACT_INDEX_REVIEW_ONLY_RECORDED",
        "contract_registry_recorded": contract_registry.get("status") == "AGENT_CONTRACT_REGISTRY_RECORDED",
        "output_schema_validation_recorded": output_schema_validation.get("status") == "AGENT_OUTPUT_SCHEMA_VALIDATION_RECORDED",
        "evals_passed": eval_report.get("passed") is True,
        "permission_policy_passed": permission_policy_report.get("passed") is True,
        "prohibited_action_scan_passed": prohibited_action_scan.get("passed") is True,
        "all_contracts_can_modify_runtime_false": contract_index.get("can_modify_runtime_all_false") is True,
        "all_contracts_can_submit_orders_false": contract_index.get("can_submit_orders_all_false") is True,
    }
    for key, ok in checks.items():
        if not ok:
            block_reasons.append(f"failed_agent_library_check:{key}")

    blocked = bool(block_reasons)
    evidence_hashes = _file_hashes(latest, REQUIRED_LATEST_EVIDENCE_FILES)
    report = {
        "agent_library_contract_review_report_version": AGENT_LIBRARY_CONTRACT_REVIEW_VERSION,
        "agent_library_contract_review_report_id": stable_id(
            "agent_library_contract_review",
            {"evidence_hashes": evidence_hashes, "checks": checks, "block_reasons": block_reasons},
            24,
        ),
        "created_at_utc": utc_now_canonical(),
        "status": STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_BLOCKED if blocked else STATUS_AGENT_LIBRARY_CONTRACT_REVIEW_RECORDED,
        "passed": not blocked,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "required_evidence_files": list(REQUIRED_LATEST_EVIDENCE_FILES),
        "missing_evidence_files": missing,
        "evidence_file_sha256": evidence_hashes,
        "checks": checks,
        "block_reasons": block_reasons,
        "agent_count": contract_index.get("agent_count", 0),
        "eval_case_count": eval_report.get("eval_case_count", 0),
        "lint_status": lint_report.get("status"),
        "contract_validation_status": contract_validation.get("status"),
        "contract_index_id": contract_index.get("agent_contract_index_id"),
        "contract_index_sha256": contract_index.get("agent_contract_index_sha256"),
        "contract_registry_record_id": contract_registry.get("agent_contract_registry_record_id"),
        "output_schema_validation_status": output_schema_validation.get("status"),
        "agent_eval_status": eval_report.get("status"),
        "permission_policy_status": permission_policy_report.get("status"),
        "prohibited_action_scan_status": prohibited_action_scan.get("status"),
    }
    report["agent_library_contract_review_report_sha256"] = sha256_json(report)
    return report


def persist_agent_library_contract_review_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    atomic_write_json(latest / "agent_library_contract_review_report.json", dict(report))
    permission_policy_report = build_agent_permission_policy_report(cfg=cfg, project_root=cfg.root)
    prohibited_action_scan = build_agent_prohibited_action_scan(cfg=cfg, project_root=cfg.root)
    atomic_write_json(latest / "agent_permission_policy_report.json", permission_policy_report)
    atomic_write_json(latest / "agent_prohibited_action_scan.json", prohibited_action_scan)
    registry_record = append_registry_record(
        registry_path(cfg, AGENT_LIBRARY_CONTRACT_REVIEW_REGISTRY_NAME),
        dict(report),
        registry_name=AGENT_LIBRARY_CONTRACT_REVIEW_REGISTRY_NAME,
        id_field="agent_library_contract_review_registry_record_id",
        hash_field="agent_library_contract_review_registry_record_sha256",
        id_prefix="agent_library_contract_review_registry",
    )
    atomic_write_json(latest / "agent_library_contract_review_registry_record.json", registry_record)
    return registry_record


def run_agent_library_contract_review_latest(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_agent_library_contract_review_report(cfg=cfg, project_root=cfg.root)
    registry_record = persist_agent_library_contract_review_report(cfg, report)
    result = dict(report)
    result["agent_library_contract_review_registry_record_id"] = registry_record.get("agent_library_contract_review_registry_record_id")
    result["agent_library_contract_review_registry_record_sha256"] = registry_record.get("agent_library_contract_review_registry_record_sha256")
    return result
