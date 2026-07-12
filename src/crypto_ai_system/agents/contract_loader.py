from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from crypto_ai_system.utils.audit import sha256_json, sha256_text

REQUIRED_FRONTMATTER_FIELDS = [
    "agent_id",
    "name",
    "division",
    "permission_tier",
    "output_schema",
    "requires_evidence",
    "can_modify_runtime",
    "can_submit_orders",
    "contract_version",
]

REQUIRED_BODY_SECTIONS = [
    "# Identity",
    "# Mission",
    "# Not Responsible For",
    "# Required Inputs",
    "# Required Checks",
    "# Failure Behavior",
    "# Required Output",
]

ALLOWED_PERMISSION_TIERS = {"read_only", "paper_only", "approval_required", "prohibited_runtime"}

PROHIBITED_RUNTIME_PHRASES = [
    "can_modify_runtime: true",
    "can_submit_orders: true",
    "runtime_mutation_performed=true",
    "order_submission_performed=true",
    "ready_for_signed_testnet_execution=true",
    "testnet_order_submission_allowed=true",
    "signed_testnet_promotion_allowed=true",
    "live_canary_execution_enabled=true",
    "live_scaled_execution_enabled=true",
    "external_order_submission_allowed=true",
    "external_order_submission_performed=true",
    "place_order_enabled=true",
    "cancel_order_enabled=true",
    "signed_order_executor_enabled=true",
    "submit live orders",
    "submit testnet orders",
    "enable place_order",
    "enable cancel_order",
    "enable signed_order_executor",
    "read api key values",
    "read api secret values",
    "read secret files",
    "create secret files",
    "mutate settings.yaml",
    "mutate runtime score_weights",
    "auto-promote to signed testnet",
    "auto-promote to live",
]


class AgentContractError(RuntimeError):
    """Raised when an Agent Library contract is malformed or unsafe."""


@dataclass(frozen=True)
class AgentContract:
    path: Path
    relative_path: str
    frontmatter: dict[str, Any]
    body: str
    raw_text: str

    @property
    def agent_id(self) -> str:
        return str(self.frontmatter.get("agent_id"))

    @property
    def division(self) -> str:
        return str(self.frontmatter.get("division"))

    @property
    def permission_tier(self) -> str:
        return str(self.frontmatter.get("permission_tier"))

    @property
    def output_schema(self) -> str:
        return str(self.frontmatter.get("output_schema"))

    @property
    def contract_version(self) -> str:
        return str(self.frontmatter.get("contract_version"))

    @property
    def contract_file_sha256(self) -> str:
        return sha256_text(self.raw_text)

    @property
    def body_sha256(self) -> str:
        return sha256_text(self.body)

    @property
    def agent_hash(self) -> str:
        return sha256_json(
            {
                "relative_path": self.relative_path,
                "frontmatter": self.frontmatter,
                "body_sha256": self.body_sha256,
                "contract_file_sha256": self.contract_file_sha256,
            }
        )

    def to_index_record(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.frontmatter.get("name"),
            "division": self.division,
            "permission_tier": self.permission_tier,
            "output_schema": self.output_schema,
            "requires_evidence": self.frontmatter.get("requires_evidence"),
            "can_modify_runtime": self.frontmatter.get("can_modify_runtime"),
            "can_submit_orders": self.frontmatter.get("can_submit_orders"),
            "contract_version": self.contract_version,
            "eval_case_path": self.frontmatter.get("eval_case_path"),
            "contract_path": self.relative_path,
            "contract_file_sha256": self.contract_file_sha256,
            "contract_body_sha256": self.body_sha256,
            "agent_hash": self.agent_hash,
        }


def parse_agent_contract(path: str | Path, *, root: str | Path = ".") -> AgentContract:
    root_path = Path(root).resolve()
    contract_path = Path(path).resolve()
    raw = contract_path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise AgentContractError(f"Missing YAML frontmatter: {contract_path}")
    parts = raw.split("---", 2)
    if len(parts) != 3:
        raise AgentContractError(f"Malformed YAML frontmatter: {contract_path}")
    frontmatter_text = parts[1]
    body = parts[2].lstrip("\n")
    frontmatter = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(frontmatter, dict):
        raise AgentContractError(f"Frontmatter must be an object: {contract_path}")
    try:
        rel = contract_path.relative_to(root_path).as_posix()
    except ValueError:
        rel = contract_path.name
    return AgentContract(
        path=contract_path,
        relative_path=rel,
        frontmatter=frontmatter,
        body=body,
        raw_text=raw,
    )


def discover_agent_contract_files(root: str | Path = ".", agents_dir: str = "agents") -> list[Path]:
    base = Path(root).resolve() / agents_dir
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.md") if path.name != "README.md")


def load_agent_contracts(root: str | Path = ".") -> list[AgentContract]:
    return [parse_agent_contract(path, root=root) for path in discover_agent_contract_files(root)]


def validate_agent_contract(contract: AgentContract) -> list[str]:
    errors: list[str] = []
    fm = contract.frontmatter
    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in fm:
            errors.append(f"{contract.relative_path}:missing_frontmatter_field:{field}")
    if fm.get("permission_tier") not in ALLOWED_PERMISSION_TIERS:
        errors.append(f"{contract.relative_path}:invalid_permission_tier:{fm.get('permission_tier')}")
    if fm.get("requires_evidence") is not True:
        errors.append(f"{contract.relative_path}:requires_evidence_not_true")
    if fm.get("can_modify_runtime") is not False:
        errors.append(f"{contract.relative_path}:can_modify_runtime_not_false")
    if fm.get("can_submit_orders") is not False:
        errors.append(f"{contract.relative_path}:can_submit_orders_not_false")
    if not str(fm.get("agent_id", "")).strip():
        errors.append(f"{contract.relative_path}:empty_agent_id")
    if not str(fm.get("output_schema", "")).endswith(".schema.json"):
        errors.append(f"{contract.relative_path}:output_schema_not_json_schema")
    eval_case_path = fm.get("eval_case_path")
    if eval_case_path is not None:
        if not isinstance(eval_case_path, str) or not eval_case_path.endswith(".json"):
            errors.append(f"{contract.relative_path}:invalid_eval_case_path")
        else:
            eval_path = contract.path.parents[2] / eval_case_path if contract.relative_path.count("/") >= 2 else Path(eval_case_path)
            # Resolve from project root rather than from the contract directory.
            project_root = contract.path
            for _ in contract.relative_path.split("/"):
                project_root = project_root.parent
            candidate = project_root / eval_case_path
            if not candidate.exists():
                errors.append(f"{contract.relative_path}:missing_eval_case_path:{eval_case_path}")
    for section in REQUIRED_BODY_SECTIONS:
        if section not in contract.body:
            errors.append(f"{contract.relative_path}:missing_body_section:{section}")
    lower_text = contract.raw_text.lower()
    # Explicitly allow prohibited phrases inside the Not Responsible For section
    # when they are used as forbidden work. Block phrases that directly flip flags
    # or state capability to enable/submit/mutate.
    strict_flag_phrases = [phrase for phrase in PROHIBITED_RUNTIME_PHRASES if phrase.endswith("=true") or phrase.endswith(": true")]
    for phrase in strict_flag_phrases:
        if phrase in lower_text:
            errors.append(f"{contract.relative_path}:prohibited_runtime_flag_phrase:{phrase}")
    if "blocked=true" not in contract.body or "fail_closed=true" not in contract.body:
        errors.append(f"{contract.relative_path}:missing_fail_closed_output_requirement")
    if "runtime_mutation_performed=false" not in contract.body:
        errors.append(f"{contract.relative_path}:missing_runtime_mutation_false_requirement")
    if "order_submission_performed=false" not in contract.body:
        errors.append(f"{contract.relative_path}:missing_order_submission_false_requirement")
    return errors


def validate_agent_contracts(root: str | Path = ".") -> tuple[list[AgentContract], list[str]]:
    contracts = load_agent_contracts(root)
    errors: list[str] = []
    if not contracts:
        errors.append("no_agent_contracts_found")
        return contracts, errors
    seen: dict[str, str] = {}
    for contract in contracts:
        errors.extend(validate_agent_contract(contract))
        agent_id = contract.agent_id
        if agent_id in seen:
            errors.append(f"duplicate_agent_id:{agent_id}:{seen[agent_id]}:{contract.relative_path}")
        else:
            seen[agent_id] = contract.relative_path
    return contracts, errors


def load_permission_policy_files(root: str | Path = ".") -> dict[str, dict[str, Any]]:
    permission_dir = Path(root).resolve() / "agent_contracts" / "permissions"
    policies: dict[str, dict[str, Any]] = {}
    if not permission_dir.exists():
        return policies
    for path in sorted(permission_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            policies[path.stem] = data
    return policies


def validate_permission_policies(root: str | Path = ".") -> list[str]:
    errors: list[str] = []
    policies = load_permission_policy_files(root)
    for required in ["read_only", "paper_only", "approval_required", "prohibited_actions"]:
        if required not in policies:
            errors.append(f"missing_permission_policy:{required}.yaml")
    prohibited = policies.get("prohibited_actions", {})
    required_false = prohibited.get("required_false_flags")
    if not isinstance(required_false, list) or "can_modify_runtime" not in required_false or "can_submit_orders" not in required_false:
        errors.append("prohibited_actions_missing_required_false_flags")
    return errors
