from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

AGENT_OUTPUT_SCHEMA_VALIDATION_REGISTRY_NAME = "agent_output_schema_validation_registry"
AGENT_OUTPUT_SCHEMA_VALIDATION_VERSION = "step323_agent_output_schema_validation_v1"

COMMON_REQUIRED_FIELDS = [
    "agent_id",
    "agent_version",
    "run_id",
    "created_at_utc",
    "input_refs",
    "output_refs",
    "passed",
    "blocked",
    "fail_closed",
    "findings",
    "warnings",
    "block_reasons",
    "evidence",
    "evidence_hash",
    "canonical_id_chain",
    "recommended_next_action",
    "runtime_mutation_performed",
    "order_submission_performed",
]

REQUIRED_CANONICAL_ID_CHAIN = [
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
    "outcome_id",
    "feedback_cycle_id",
]

_EXPECTED_TYPES = {
    "agent_id": str,
    "agent_version": str,
    "run_id": str,
    "created_at_utc": str,
    "input_refs": dict,
    "output_refs": dict,
    "passed": bool,
    "blocked": bool,
    "fail_closed": bool,
    "findings": list,
    "warnings": list,
    "block_reasons": list,
    "evidence": list,
    "evidence_hash": str,
    "canonical_id_chain": dict,
    "recommended_next_action": str,
    "runtime_mutation_performed": bool,
    "order_submission_performed": bool,
}


@dataclass(frozen=True)
class AgentOutputValidationResult:
    status: str
    passed: bool
    blocked: bool
    fail_closed: bool
    block_reasons: list[str]
    warnings: list[str]
    output_hash: str | None
    validation_id: str

    def to_record(self, *, agent_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        record = {
            "agent_output_schema_validation_version": AGENT_OUTPUT_SCHEMA_VALIDATION_VERSION,
            "agent_output_schema_validation_id": self.validation_id,
            "created_at_utc": utc_now_canonical(),
            "agent_id": agent_id,
            "run_id": run_id,
            "status": self.status,
            "passed": self.passed,
            "blocked": self.blocked,
            "fail_closed": self.fail_closed,
            "block_reasons": self.block_reasons,
            "warnings": self.warnings,
            "output_hash": self.output_hash,
            "review_only": True,
            "runtime_permission_source": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "runtime_mutation_performed": False,
            "order_submission_performed": False,
            "auto_promotion_allowed": False,
        }
        record["agent_output_schema_validation_sha256"] = sha256_json(record)
        return record


def _atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def load_json_file(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def validate_agent_output(output: Mapping[str, Any]) -> AgentOutputValidationResult:
    reasons: list[str] = []
    warnings: list[str] = []

    for field in COMMON_REQUIRED_FIELDS:
        if field not in output:
            reasons.append(f"missing_required_field:{field}")

    for field, expected_type in _EXPECTED_TYPES.items():
        if field in output and not isinstance(output.get(field), expected_type):
            reasons.append(f"invalid_type:{field}:expected_{expected_type.__name__}")

    if isinstance(output.get("created_at_utc"), str) and not is_canonical_utc_timestamp(output.get("created_at_utc")):
        reasons.append("non_canonical_created_at_utc")

    if output.get("runtime_mutation_performed") is True:
        reasons.append("prohibited_runtime_mutation_performed")
    if output.get("order_submission_performed") is True:
        reasons.append("prohibited_order_submission_performed")

    evidence_hash = output.get("evidence_hash")
    if not isinstance(evidence_hash, str) or not evidence_hash.strip():
        reasons.append("missing_evidence_hash")

    evidence = output.get("evidence")
    if isinstance(evidence, list) and not evidence:
        reasons.append("missing_evidence")

    chain = output.get("canonical_id_chain")
    if not isinstance(chain, dict):
        reasons.append("missing_canonical_id_chain")
    else:
        missing_chain = [key for key in REQUIRED_CANONICAL_ID_CHAIN if not str(chain.get(key, "")).strip()]
        if missing_chain:
            reasons.append("broken_canonical_id_chain:" + ",".join(missing_chain))

    # If the output itself says it is blocked or uncertain, it must fail closed.
    if output.get("blocked") is True and output.get("fail_closed") is not True:
        reasons.append("blocked_output_not_fail_closed")
    if output.get("passed") is True and output.get("blocked") is True:
        reasons.append("contradictory_passed_and_blocked")

    if reasons and output.get("blocked") is not True:
        warnings.append("validator_forced_blocked_true_due_to_schema_or_safety_violation")
    if reasons and output.get("fail_closed") is not True:
        warnings.append("validator_forced_fail_closed_true_due_to_schema_or_safety_violation")

    output_hash = sha256_json(dict(output)) if isinstance(output, Mapping) else None
    forced_block = bool(reasons)
    status = "PASS_REVIEW_ONLY" if not reasons and output.get("blocked") is not True else "BLOCK_FAIL_CLOSED"
    payload = {
        "status": status,
        "reasons": reasons,
        "output_hash": output_hash,
        "agent_id": output.get("agent_id"),
        "run_id": output.get("run_id"),
    }
    return AgentOutputValidationResult(
        status=status,
        passed=not reasons and output.get("passed") is True and output.get("blocked") is False,
        blocked=forced_block or output.get("blocked") is True,
        fail_closed=forced_block or output.get("fail_closed") is True,
        block_reasons=reasons + [str(reason) for reason in output.get("block_reasons", []) if output.get("blocked") is True],
        warnings=warnings,
        output_hash=output_hash,
        validation_id=stable_id("agent_output_schema_validation", payload, 24),
    )


def validate_agent_output_file(path: str | Path) -> AgentOutputValidationResult:
    return validate_agent_output(load_json_file(path))


def build_agent_output_schema_validation_report(outputs: list[Mapping[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for output in outputs:
        result = validate_agent_output(output)
        records.append(result.to_record(agent_id=str(output.get("agent_id")), run_id=str(output.get("run_id"))))
    blocked_count = sum(1 for record in records if record["blocked"])
    unsafe_count = sum(
        1
        for record in records
        if any(
            reason in record.get("block_reasons", [])
            for reason in ["prohibited_runtime_mutation_performed", "prohibited_order_submission_performed"]
        )
    )
    report = {
        "agent_output_schema_validation_report_version": AGENT_OUTPUT_SCHEMA_VALIDATION_VERSION,
        "created_at_utc": utc_now_canonical(),
        "status": "AGENT_OUTPUT_SCHEMA_VALIDATION_RECORDED" if records else "AGENT_OUTPUT_SCHEMA_VALIDATION_BLOCKED",
        "passed": bool(records) and unsafe_count == 0,
        "review_only": True,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "runtime_mutation_performed": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "output_count": len(records),
        "blocked_count": blocked_count,
        "unsafe_output_count": unsafe_count,
        "records": records,
    }
    report["agent_output_schema_validation_report_sha256"] = sha256_json(report)
    return report


def persist_agent_output_schema_validation_report(cfg: AppConfig, report: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    _atomic_write_json(latest / "agent_output_schema_validation_report.json", report)
    appended = append_registry_record(
        registry_path(cfg, AGENT_OUTPUT_SCHEMA_VALIDATION_REGISTRY_NAME),
        report,
        registry_name=AGENT_OUTPUT_SCHEMA_VALIDATION_REGISTRY_NAME,
        id_field="agent_output_schema_validation_append_id",
        hash_field="agent_output_schema_validation_append_sha256",
        id_prefix="agent_output_schema_validation_append",
    )
    _atomic_write_json(latest / "agent_output_schema_validation_registry_record.json", appended)
    return appended
