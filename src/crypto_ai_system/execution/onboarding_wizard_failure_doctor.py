from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.non_developer_onboarding_wizard import (
    STATUS_BLOCKED_FAIL_CLOSED as P36_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P36_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P36_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_VERSION = "p37_onboarding_wizard_failure_doctor_v1"
P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_REGISTRY_NAME = "p37_onboarding_wizard_failure_doctor_registry"

STATUS_GENERATED_REVIEW_ONLY = "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_BLOCKED_FAIL_CLOSED"

_REQUIRED_ROOT_PATHS = (
    "README.md",
    "scripts",
    "src",
    "src/crypto_ai_system",
    "storage",
    "storage/latest",
)
_REQUIRED_P36_ARTIFACTS = (
    "p36_non_developer_onboarding_wizard_report.json",
    "p36_non_developer_onboarding_wizard_summary.json",
    "p36_non_developer_onboarding_wizard_pack.json",
    "p36_onboarding_wizard_steps.json",
    "p36_zip_drop_in_wizard.md",
    "p36_zip_drop_in_checklist.md",
    "p36_failure_message_lookup.md",
    "p36_operator_onboarding_card.json",
)
_REQUIRED_LOOKUP_CODES = (
    "no_zip_found",
    "bad_zip_structure",
    "missing_scripts",
    "missing_src_package",
    "missing_storage_latest",
    "missing_p36_artifacts",
    "blocked_command_attempt",
    "secret_detected",
    "runtime_flag_truthy",
    "scheduler_enabled",
    "endpoint_called",
    "p36_waiting",
    "p36_blocked",
)
_BLOCKED_COMMAND_KEYWORDS = (
    "enable",
    "start",
    "submit",
    "order",
    "live",
    "trade",
    "activate",
    "scheduler",
    "place",
    "cancel",
    "runtime",
)
_ALLOWED_READ_ONLY_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
_EXECUTION_FIELDS_FOR_P37 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "runtime_enablement_performed",
    "operator_runtime_activation_performed",
    "final_activation_gate_performed",
    "actual_live_order_submitted",
    "actual_testnet_order_submitted",
    "live_order_endpoint_called",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_file_accessed",
    "secret_file_created",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "runtime_authority_claimed",
    "failure_doctor_executes_runtime",
    "failure_doctor_enables_scheduler",
    "failure_doctor_allows_order_submission",
    "failure_doctor_calls_endpoint",
    "failure_doctor_reads_secret_value",
    "self_diagnosis_allows_runtime",
    "operator_fix_action_enables_runtime",
}
_SECRET_VALUE_PATTERNS = (
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "PRIVATE_KEY=",
    "api_secret_value:",
    "api_key_value:",
    "secret_value:",
    "BEGIN PRIVATE KEY",
)


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any] | list[Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, list):
        return list(payload)
    return {}


def _read_latest_text(cfg: AppConfig, filename: str) -> str:
    path = _latest_dir(cfg) / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P37 and _bool(value):
                    hits.append({"source": source, "path": next_path, "field": str(key), "value": True})
                walk(value, source, next_path)
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _scan_secret_value_patterns(payloads: Sequence[tuple[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                walk(value, source, f"{path}.{key}")
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")
        elif isinstance(payload, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in payload.lower():
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def _detect_blocked_command_attempt(command_log: Sequence[str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for raw in command_log:
        command = str(raw).strip()
        lowered = command.lower()
        for keyword in _BLOCKED_COMMAND_KEYWORDS:
            if keyword in lowered:
                hits.append({"command": command, "matched_keyword": keyword, "route": "ROUTE_BLOCKED_FAIL_CLOSED"})
                break
    return hits


def _diagnosis_lookup() -> list[dict[str, str]]:
    return [
        {"code": "no_zip_found", "meaning": "ZIP 파일이 import/drop-in 위치에서 보이지 않는다.", "operator_action": "ZIP 파일명을 확인하고 다시 붙여넣는다. 실행 명령은 누르지 않는다."},
        {"code": "bad_zip_structure", "meaning": "압축 해제 후 기본 폴더 구조가 맞지 않는다.", "operator_action": "README.md, scripts, src, storage가 보이는지 확인하고 원본 ZIP으로 다시 시도한다."},
        {"code": "missing_scripts", "meaning": "scripts 폴더가 없어 조회 명령을 실행할 수 없다.", "operator_action": "ZIP을 다시 풀고 scripts/run_* 파일이 있는지 확인한다."},
        {"code": "missing_src_package", "meaning": "src/crypto_ai_system 패키지가 없어 Python import가 실패할 수 있다.", "operator_action": "ZIP 구조를 확인하고 잘못된 상위 폴더에서 실행 중인지 확인한다."},
        {"code": "missing_storage_latest", "meaning": "storage/latest가 없어 latest artifact 조회가 불가능하다.", "operator_action": "P31~P36 dashboard/runbook artifact를 먼저 재생성한다."},
        {"code": "missing_p36_artifacts", "meaning": "P36 onboarding wizard 산출물이 부족하다.", "operator_action": "P36 wizard command를 재실행한 뒤 status만 확인한다."},
        {"code": "blocked_command_attempt", "meaning": "enable/start/submit/order/live 계열 명령 시도가 감지되었다.", "operator_action": "해당 명령을 중단하고 status/matrix/waiting/no_go/export_paths만 사용한다."},
        {"code": "secret_detected", "meaning": "API key/secret/private key/passphrase 같은 secret 흔적이 감지되었다.", "operator_action": "secret 값을 제거하고 metadata-only reference만 남긴다."},
        {"code": "runtime_flag_truthy", "meaning": "runtime/order/scheduler 관련 flag가 true로 감지되었다.", "operator_action": "패키지를 격리하고 runtime activation을 중단한다."},
        {"code": "scheduler_enabled", "meaning": "scheduler가 enabled 상태로 보인다.", "operator_action": "scheduler/start/activate 계열을 중단하고 review-only ZIP으로 롤백한다."},
        {"code": "endpoint_called", "meaning": "order/status/cancel/http endpoint call evidence가 감지되었다.", "operator_action": "실행을 중단하고 endpoint evidence를 별도 incident로 검토한다."},
        {"code": "p36_waiting", "meaning": "P36 source가 waiting 상태다.", "operator_action": "부족한 P35/P36 artifact를 먼저 확인한다."},
        {"code": "p36_blocked", "meaning": "P36 source가 blocked 상태다.", "operator_action": "block reason을 먼저 제거하기 전에는 다음 단계로 가지 않는다."},
    ]


def _root_structure_issues(root: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for rel in _REQUIRED_ROOT_PATHS:
        if not (root / rel).exists():
            code = "bad_zip_structure"
            if rel == "scripts":
                code = "missing_scripts"
            elif rel == "src/crypto_ai_system":
                code = "missing_src_package"
            elif rel == "storage/latest":
                code = "missing_storage_latest"
            issues.append({"code": code, "path": rel, "severity": "waiting"})
    return issues


def _build_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# P37 Onboarding Wizard Failure Doctor / Self-Diagnosis Pack",
        "",
        f"Status: `{pack.get('status')}`",
        f"Decision: `{pack.get('operator_final_activation_decision')}`",
        "",
        "> 이 self-diagnosis pack은 review-only입니다. runtime, scheduler, order, endpoint, secret access를 활성화하지 않습니다.",
        "",
        "## Detected Issues",
        "",
    ]
    issues = pack.get("diagnosis_results", [])
    if not issues:
        lines.append("- No blocking diagnosis issues detected. Runtime still remains DISABLED.")
    else:
        for issue in issues:
            lines.append(f"- `{issue.get('code')}` / severity=`{issue.get('severity')}`: {issue.get('message')}")
    lines.extend(["", "## Allowed Commands", ""])
    for command in _ALLOWED_READ_ONLY_COMMANDS:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Blocked Command Keywords", ""])
    for keyword in _BLOCKED_COMMAND_KEYWORDS:
        lines.append(f"- `{keyword}`")
    lines.extend(["", "## Diagnosis Lookup", ""])
    for item in pack.get("diagnosis_lookup", []):
        lines.extend([f"### `{item.get('code')}`", "", f"의미: {item.get('meaning')}", "", f"운영자 조치: {item.get('operator_action')}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _build_checklist(pack: Mapping[str, Any]) -> str:
    lines = ["# P37 Operator Self-Diagnosis Checklist", ""]
    for item in pack.get("operator_self_diagnosis_checklist", []):
        lines.append(f"- [ ] {item}")
    return "\n".join(lines).rstrip() + "\n"


def _build_operator_card(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "card_id": "p37_onboarding_failure_doctor_card",
        "title": "Crypto_AI_System Self-Diagnosis",
        "status": pack.get("status"),
        "decision": pack.get("operator_final_activation_decision"),
        "issue_count": pack.get("diagnosis_issue_count"),
        "blocked_issue_count": pack.get("blocked_issue_count"),
        "waiting_issue_count": pack.get("waiting_issue_count"),
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "authority": "REVIEW_ONLY",
        "allowed_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "operator_next_action": "Resolve diagnosis issues, then use status/matrix/waiting/no_go/export_paths only.",
        "runtime_authority": False,
    }


def build_onboarding_wizard_failure_doctor_report(
    *,
    root: str | Path | None = None,
    zip_found: bool = True,
    command_log: Sequence[str] = (),
    p36_report: Mapping[str, Any] | None = None,
    p36_summary: Mapping[str, Any] | None = None,
    p36_pack: Mapping[str, Any] | None = None,
    p36_wizard_markdown: str | None = None,
    p36_checklist_markdown: str | None = None,
    p36_failure_lookup_markdown: str | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)
    root_path = cfg.root

    if p36_report is None:
        p36_report = _read_latest_json(cfg, "p36_non_developer_onboarding_wizard_report.json")
    if p36_summary is None:
        p36_summary = _read_latest_json(cfg, "p36_non_developer_onboarding_wizard_summary.json")
    if p36_pack is None:
        loaded = _read_latest_json(cfg, "p36_non_developer_onboarding_wizard_pack.json")
        p36_pack = loaded if isinstance(loaded, Mapping) else {}
    if p36_wizard_markdown is None:
        p36_wizard_markdown = _read_latest_text(cfg, "p36_zip_drop_in_wizard.md")
    if p36_checklist_markdown is None:
        p36_checklist_markdown = _read_latest_text(cfg, "p36_zip_drop_in_checklist.md")
    if p36_failure_lookup_markdown is None:
        p36_failure_lookup_markdown = _read_latest_text(cfg, "p36_failure_message_lookup.md")

    missing_p36_artifacts = [name for name in _REQUIRED_P36_ARTIFACTS if not (latest / name).exists()]
    structure_issues = _root_structure_issues(root_path)
    blocked_command_hits = _detect_blocked_command_attempt(command_log)
    payloads: list[tuple[str, Any]] = [
        ("p36_report", dict(p36_report)),
        ("p36_summary", dict(p36_summary)),
        ("p36_pack", dict(p36_pack)),
        ("p36_wizard_markdown", p36_wizard_markdown),
        ("p36_checklist_markdown", p36_checklist_markdown),
        ("p36_failure_lookup_markdown", p36_failure_lookup_markdown),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(payloads)
    secret_hits = _scan_secret_value_patterns(payloads)

    p36_status = str(p36_report.get("status", "")) if isinstance(p36_report, Mapping) else ""
    diagnosis_results: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, evidence: Any = None) -> None:
        issue = {"code": code, "severity": severity, "message": message}
        if evidence is not None:
            issue["evidence"] = evidence
        diagnosis_results.append(issue)

    if not zip_found:
        add_issue("no_zip_found", "waiting", "ZIP file was not found in the expected drop-in location.")
    for issue in structure_issues:
        add_issue(issue["code"], "waiting", f"Required path is missing: {issue['path']}", issue)
    if missing_p36_artifacts:
        add_issue("missing_p36_artifacts", "waiting", "Required P36 onboarding artifacts are missing.", missing_p36_artifacts)
    if not p36_report:
        add_issue("missing_p36_artifacts", "waiting", "P36 report is missing or empty.")
    if p36_status == P36_STATUS_WAITING_REVIEW_ONLY or _bool(p36_report.get("waiting")):
        add_issue("p36_waiting", "waiting", "Source P36 wizard is waiting.")
    if p36_status == P36_STATUS_BLOCKED_FAIL_CLOSED or _bool(p36_report.get("blocked")):
        add_issue("p36_blocked", "blocked", "Source P36 wizard is blocked fail-closed.")
    if p36_status and p36_status != P36_STATUS_GENERATED_REVIEW_ONLY:
        add_issue("p36_waiting", "waiting", f"Source P36 status is not generated: {p36_status}")
    if blocked_command_hits:
        add_issue("blocked_command_attempt", "blocked", "Unsafe command attempt was detected.", blocked_command_hits)
    if unsafe_hits:
        add_issue("runtime_flag_truthy", "blocked", "Truthy runtime/order/scheduler flag was detected.", unsafe_hits)
        scheduler_specific = [hit for hit in unsafe_hits if "scheduler" in hit.get("field", "")]
        endpoint_specific = [hit for hit in unsafe_hits if "endpoint" in hit.get("field", "") or hit.get("field") == "http_request_sent"]
        if scheduler_specific:
            add_issue("scheduler_enabled", "blocked", "Scheduler-related truthy flag was detected.", scheduler_specific)
        if endpoint_specific:
            add_issue("endpoint_called", "blocked", "Endpoint-call truthy flag was detected.", endpoint_specific)
    if secret_hits:
        add_issue("secret_detected", "blocked", "Secret value pattern was detected.", secret_hits)

    blocked = any(issue["severity"] == "blocked" for issue in diagnosis_results)
    waiting = bool(diagnosis_results) and not blocked
    status = STATUS_GENERATED_REVIEW_ONLY
    if waiting:
        status = STATUS_WAITING_REVIEW_ONLY
    if blocked:
        status = STATUS_BLOCKED_FAIL_CLOSED

    operator_checklist = [
        "ZIP 파일이 drop-in 위치에 있는지 확인한다.",
        "README.md, scripts, src, storage/latest가 보이는지 확인한다.",
        "P36 onboarding wizard artifacts가 storage/latest에 있는지 확인한다.",
        "status/matrix/waiting/no_go/export_paths만 사용한다.",
        "enable/start/submit/order/live/trade/activate/scheduler/place/cancel/runtime 명령 시도를 중단한다.",
        "API key/secret/private key/passphrase를 입력하거나 저장하지 않는다.",
        "runtime/order/scheduler flag가 true면 즉시 fail-closed로 간주한다.",
        "endpoint called evidence가 있으면 incident로 분리한다.",
        "self-diagnosis pack은 실행 권한이 아님을 이해한다.",
    ]

    pack: dict[str, Any] = {
        "version": P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_VERSION,
        "status": status,
        "waiting": waiting,
        "blocked": blocked,
        "created_at_utc": utc_now_canonical(),
        "source_p36_status": p36_status or None,
        "source_p36_report_sha256": sha256_json(p36_report) if p36_report else None,
        "source_p36_pack_sha256": sha256_json(p36_pack) if p36_pack else None,
        "operator_final_activation_decision": p36_pack.get("operator_final_activation_decision") or p36_report.get("operator_final_activation_decision") or "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "diagnosis_results": diagnosis_results,
        "diagnosis_issue_count": len(diagnosis_results),
        "blocked_issue_count": sum(1 for issue in diagnosis_results if issue["severity"] == "blocked"),
        "waiting_issue_count": sum(1 for issue in diagnosis_results if issue["severity"] == "waiting"),
        "diagnosis_codes": sorted({issue["code"] for issue in diagnosis_results}),
        "diagnosis_lookup": _diagnosis_lookup(),
        "diagnosis_lookup_count": len(_diagnosis_lookup()),
        "required_lookup_codes_present": all(code in {item["code"] for item in _diagnosis_lookup()} for code in _REQUIRED_LOOKUP_CODES),
        "root_structure_issues": structure_issues,
        "missing_p36_artifacts": missing_p36_artifacts,
        "blocked_command_attempts": blocked_command_hits,
        "blocked_command_attempt_count": len(blocked_command_hits),
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "secret_value_pattern_hits": secret_hits,
        "secret_value_pattern_hit_count": len(secret_hits),
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_BLOCKED_COMMAND_KEYWORDS),
        "operator_self_diagnosis_checklist": operator_checklist,
        "operator_self_diagnosis_checklist_item_count": len(operator_checklist),
        "all_self_diagnosis_artifacts_safe_review_only": not blocked,
        "runtime_authority": False,
        "failure_doctor_executes_runtime": False,
        "failure_doctor_enables_scheduler": False,
        "failure_doctor_allows_order_submission": False,
        "failure_doctor_calls_endpoint": False,
        "failure_doctor_reads_secret_value": False,
        "self_diagnosis_allows_runtime": False,
        "operator_fix_action_enables_runtime": False,
        **{key: False for key in _EXECUTION_FIELDS_FOR_P37 if key not in {"failure_doctor_executes_runtime", "failure_doctor_enables_scheduler", "failure_doctor_allows_order_submission", "failure_doctor_calls_endpoint", "failure_doctor_reads_secret_value", "self_diagnosis_allows_runtime", "operator_fix_action_enables_runtime"}},
        "execution_flags": default_execution_flag_state(),
        "truthy_default_execution_flags": truthy_execution_flags(default_execution_flag_state()),
    }
    pack["self_diagnosis_markdown"] = _build_markdown(pack)
    pack["self_diagnosis_checklist_markdown"] = _build_checklist(pack)
    pack["operator_self_diagnosis_card"] = _build_operator_card(pack)
    pack["report_id"] = stable_id("p37_failure_doctor", pack)
    return pack


def build_p37_negative_fixture_results(*, root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    base_report = {
        "status": P36_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    base_summary = {"status": P36_STATUS_GENERATED_REVIEW_ONLY, "blocked": False, "waiting": False}
    base_pack = {
        "status": P36_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
    }
    text = "Runtime: DISABLED\nScheduler: DISABLED\nOrders: DISABLED\n"
    bad_structure_root = cfg.root / "p37_bad_zip_structure_fixture"
    (bad_structure_root / "config").mkdir(parents=True, exist_ok=True)
    (bad_structure_root / "config" / "settings.yaml").write_text(
        "project:\n  name: p37-bad-structure-fixture\n  version: test\n"
        "storage:\n  latest_dir: storage/latest\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )

    cases: dict[str, dict[str, Any]] = {
        "no_zip_found": {"zip_found": False},
        "bad_zip_structure": {"root": bad_structure_root},
        "missing_p36_report": {"p36_report": {}},
        "p36_waiting": {"p36_report": {**base_report, "status": P36_STATUS_WAITING_REVIEW_ONLY, "waiting": True}},
        "p36_blocked": {"p36_report": {**base_report, "status": P36_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}},
        "blocked_command_attempt": {"command_log": ["/crypto_live", "submit order"]},
        "secret_detected": {"p36_wizard_markdown": "BINANCE_API_SECRET=leak"},
        "runtime_flag_truthy": {"p36_report": {**base_report, "live_scaled_execution_enabled": True}},
        "scheduler_enabled": {"p36_summary": {**base_summary, "runtime_scheduler_enabled": True}},
        "endpoint_called": {"p36_report": {**base_report, "order_endpoint_called": True}},
        "failure_doctor_executes_runtime": {"extra_payloads_for_scan": [("bad_doctor", {"failure_doctor_executes_runtime": True})]},
        "self_diagnosis_allows_runtime": {"extra_payloads_for_scan": [("bad_self_diagnosis", {"self_diagnosis_allows_runtime": True})]},
    }
    fixtures: dict[str, dict[str, Any]] = {}
    for case, overrides in cases.items():
        case_root = overrides.get("root", cfg.root)
        report = build_onboarding_wizard_failure_doctor_report(
            root=case_root,
            zip_found=overrides.get("zip_found", True),
            command_log=overrides.get("command_log", ()),
            p36_report=overrides.get("p36_report", base_report),
            p36_summary=overrides.get("p36_summary", base_summary),
            p36_pack=overrides.get("p36_pack", base_pack),
            p36_wizard_markdown=overrides.get("p36_wizard_markdown", text),
            p36_checklist_markdown=overrides.get("p36_checklist_markdown", text),
            p36_failure_lookup_markdown=overrides.get("p36_failure_lookup_markdown", text),
            extra_payloads_for_scan=overrides.get("extra_payloads_for_scan", ()),
        )
        fixtures[case] = {
            "status": report["status"],
            "blocked": bool(report["blocked"]),
            "waiting": bool(report["waiting"]),
            "diagnosis_codes": report["diagnosis_codes"],
        }
    all_safe = all(item["blocked"] or item["waiting"] for item in fixtures.values())
    return {
        "status": "P37_NEGATIVE_FIXTURES_RECORDED",
        "fixture_results": fixtures,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_safe,
        "created_at_utc": utc_now_canonical(),
    }


def persist_onboarding_wizard_failure_doctor(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p37_onboarding_wizard_failure_doctor")
    report = build_onboarding_wizard_failure_doctor_report(root=cfg.root)
    negative = build_p37_negative_fixture_results(root=cfg.root)

    report_path = latest / "p37_onboarding_wizard_failure_doctor_report.json"
    summary_path = latest / "p37_onboarding_wizard_failure_doctor_summary.json"
    pack_path = latest / "p37_onboarding_wizard_failure_doctor_pack.json"
    diagnosis_path = latest / "p37_self_diagnosis_results.json"
    lookup_path = latest / "p37_failure_doctor_lookup.json"
    markdown_path = latest / "p37_self_diagnosis_pack.md"
    checklist_path = latest / "p37_self_diagnosis_checklist.md"
    card_path = latest / "p37_operator_self_diagnosis_card.json"
    negative_path = latest / "p37_onboarding_wizard_failure_doctor_negative_fixture_results.json"
    registry_record_path = latest / "p37_onboarding_wizard_failure_doctor_registry_record.json"

    atomic_write_json(report_path, report)
    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "diagnosis_issue_count": report["diagnosis_issue_count"],
        "blocked_issue_count": report["blocked_issue_count"],
        "waiting_issue_count": report["waiting_issue_count"],
        "diagnosis_codes": report["diagnosis_codes"],
        "allowed_read_only_commands": report["allowed_read_only_commands"],
        "blocked_command_keywords": report["blocked_command_keywords"],
        "all_self_diagnosis_artifacts_safe_review_only": report["all_self_diagnosis_artifacts_safe_review_only"],
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "self_diagnosis_paths": {
            "markdown": str(markdown_path),
            "checklist": str(checklist_path),
            "diagnosis_results": str(diagnosis_path),
            "lookup": str(lookup_path),
            "operator_card": str(card_path),
        },
    }
    atomic_write_json(summary_path, summary)
    atomic_write_json(pack_path, {k: v for k, v in report.items() if k not in {"self_diagnosis_markdown", "self_diagnosis_checklist_markdown"}})
    atomic_write_json(diagnosis_path, report["diagnosis_results"])
    atomic_write_json(lookup_path, report["diagnosis_lookup"])
    _atomic_write_text(markdown_path, report["self_diagnosis_markdown"])
    _atomic_write_text(checklist_path, report["self_diagnosis_checklist_markdown"])
    atomic_write_json(card_path, report["operator_self_diagnosis_card"])
    atomic_write_json(negative_path, negative)

    atomic_write_json(storage / report_path.name, report)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / pack_path.name, {k: v for k, v in report.items() if k not in {"self_diagnosis_markdown", "self_diagnosis_checklist_markdown"}})
    atomic_write_json(storage / diagnosis_path.name, report["diagnosis_results"])
    atomic_write_json(storage / lookup_path.name, report["diagnosis_lookup"])
    _atomic_write_text(storage / markdown_path.name, report["self_diagnosis_markdown"])
    _atomic_write_text(storage / checklist_path.name, report["self_diagnosis_checklist_markdown"])
    atomic_write_json(storage / card_path.name, report["operator_self_diagnosis_card"])

    registry_record = {
        "registry_record_id": stable_id("p37_registry_record", report),
        "report_id": report["report_id"],
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "diagnosis_issue_count": report["diagnosis_issue_count"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    atomic_write_json(registry_record_path, registry_record)
    append_registry_record(
        registry_path(cfg, P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_REGISTRY_NAME),
        registry_record,
        registry_name=P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_REGISTRY_NAME,
    )
    return report


__all__ = [
    "P37_ONBOARDING_WIZARD_FAILURE_DOCTOR_VERSION",
    "STATUS_GENERATED_REVIEW_ONLY",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "build_onboarding_wizard_failure_doctor_report",
    "build_p37_negative_fixture_results",
    "persist_onboarding_wizard_failure_doctor",
]
