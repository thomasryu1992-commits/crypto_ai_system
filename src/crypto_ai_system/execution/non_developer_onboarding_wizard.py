from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_ux_quickstart_runbook_pack import (
    STATUS_BLOCKED_FAIL_CLOSED as P35_STATUS_BLOCKED_FAIL_CLOSED,
    STATUS_GENERATED_REVIEW_ONLY as P35_STATUS_GENERATED_REVIEW_ONLY,
    STATUS_WAITING_REVIEW_ONLY as P35_STATUS_WAITING_REVIEW_ONLY,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P36_NON_DEVELOPER_ONBOARDING_WIZARD_VERSION = "p36_non_developer_onboarding_wizard_v1"
P36_NON_DEVELOPER_ONBOARDING_WIZARD_REGISTRY_NAME = "p36_non_developer_onboarding_wizard_registry"

STATUS_GENERATED_REVIEW_ONLY = "P36_NON_DEVELOPER_ONBOARDING_WIZARD_GENERATED_REVIEW_ONLY"
STATUS_WAITING_REVIEW_ONLY = "P36_NON_DEVELOPER_ONBOARDING_WIZARD_WAITING_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P36_NON_DEVELOPER_ONBOARDING_WIZARD_BLOCKED_FAIL_CLOSED"

_ALLOWED_READ_ONLY_COMMANDS = ("status", "matrix", "waiting", "no_go", "export_paths")
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
_REQUIRED_P35_ARTIFACTS = (
    "p35_operator_ux_quickstart_runbook_pack_report.json",
    "p35_operator_ux_quickstart_runbook_pack_summary.json",
    "p35_operator_ux_quickstart_runbook_pack.json",
    "p35_operator_ux_quickstart_runbook.md",
    "p35_operator_ux_checklist.md",
    "p35_safe_command_guide.md",
    "p35_operator_ux_quickstart.txt",
)
_EXECUTION_FIELDS_FOR_P36 = {
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
    "wizard_executes_runtime",
    "wizard_enables_scheduler",
    "wizard_allows_order_submission",
    "wizard_calls_endpoint",
    "wizard_reads_secret_value",
    "drop_in_guide_enables_runtime",
    "drop_in_guide_allows_order_submission",
    "failure_lookup_allows_runtime",
    "operator_onboarding_card_allows_runtime",
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
                if key in _EXECUTION_FIELDS_FOR_P36 and _bool(value):
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


def _build_wizard_steps() -> list[dict[str, Any]]:
    return [
        {
            "step_id": "zip_drop_in",
            "title": "ZIP 붙여넣기",
            "operator_action": "Thomas Agent OS 또는 로컬 작업 폴더의 import/inbox 위치에 Crypto_AI_System ZIP을 넣는다.",
            "expected_result": "ZIP 파일명이 보이고 압축이 손상되지 않았다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "import_or_unpack",
            "title": "Import 또는 압축 해제",
            "operator_action": "Launcher import 또는 로컬 unzip을 수행한다. 이 단계는 파일 배치만 확인한다.",
            "expected_result": "프로젝트 루트에 README.md, scripts, src, storage 폴더가 보인다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "read_only_status",
            "title": "상태 확인",
            "operator_action": "status 명령 또는 run_command_response_snapshot_pack.py --print-telegram 을 실행한다.",
            "expected_result": "Decision이 WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE로 표시되고 Runtime/Scheduler/Orders가 DISABLED로 표시된다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "matrix_review",
            "title": "Matrix 확인",
            "operator_action": "matrix 또는 waiting 명령으로 어떤 phase가 기다리는지 확인한다.",
            "expected_result": "P7 이후의 외부 evidence/operator evidence 대기 항목이 표시된다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "no_go_review",
            "title": "No-Go 확인",
            "operator_action": "no_go 명령으로 차단 항목이 있는지 확인한다.",
            "expected_result": "No-Go가 없거나, 있으면 운영자가 수정 전 다음 단계로 가지 않는다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "export_paths_review",
            "title": "Export 경로 확인",
            "operator_action": "export_paths 명령으로 Markdown/CSV/Telegram/Launcher snapshot 위치를 확인한다.",
            "expected_result": "storage/latest 아래 dashboard, checklist, snapshot artifact 경로가 표시된다.",
            "safe_only": True,
            "executes_runtime": False,
        },
        {
            "step_id": "stop_before_runtime",
            "title": "실행 전 정지",
            "operator_action": "enable/start/submit/order/live/trade/activate/scheduler/place/cancel/runtime 계열 명령을 실행하지 않는다.",
            "expected_result": "자동매매와 주문 제출은 계속 비활성 상태다.",
            "safe_only": True,
            "executes_runtime": False,
        },
    ]


def _failure_lookup() -> list[dict[str, str]]:
    return [
        {
            "message_contains": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
            "meaning": "아직 실제 signed testnet/live/canary/CI/operator evidence가 부족하다.",
            "operator_action": "status, waiting, export_paths만 확인하고 실행 명령은 누르지 않는다.",
        },
        {
            "message_contains": "Runtime: DISABLED",
            "meaning": "정상이다. 현재 패키지는 review-only 상태다.",
            "operator_action": "Dashboard 조회만 진행한다.",
        },
        {
            "message_contains": "Scheduler: DISABLED",
            "meaning": "정상이다. 자동 루프는 시작되지 않았다.",
            "operator_action": "scheduler/start/activate 계열 명령을 실행하지 않는다.",
        },
        {
            "message_contains": "Orders: DISABLED",
            "meaning": "정상이다. 주문 제출은 열리지 않았다.",
            "operator_action": "submit/order/place/cancel 계열 명령을 실행하지 않는다.",
        },
        {
            "message_contains": "ROUTE_BLOCKED_FAIL_CLOSED",
            "meaning": "위험 명령이 안전하게 차단되었다.",
            "operator_action": "해당 명령을 반복하지 말고 status/matrix/waiting만 조회한다.",
        },
        {
            "message_contains": "P35_SOURCE_P34",
            "meaning": "P34 snapshot artifact가 없거나 손상되었다.",
            "operator_action": "P34 snapshot pack을 먼저 재생성한다.",
        },
        {
            "message_contains": "secret",
            "meaning": "secret 관련 흔적이 감지될 수 있다.",
            "operator_action": "API key/secret/private key/passphrase를 제거하고 패키지를 다시 검증한다.",
        },
    ]


def _build_zip_drop_in_markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# P36 Non-Developer Onboarding Wizard / ZIP Drop-in Guide",
        "",
        f"Status: `{pack.get('status')}`",
        f"Decision: `{pack.get('operator_final_activation_decision')}`",
        "",
        "이 문서는 비개발자 운영자가 Crypto_AI_System ZIP을 붙여넣고 안전하게 상태만 확인하기 위한 wizard입니다.",
        "",
        "> 이 wizard는 review-only입니다. runtime, scheduler, live/testnet order, secret access를 활성화하지 않습니다.",
        "",
        "## 허용되는 조회 명령",
        "",
    ]
    for command in _ALLOWED_READ_ONLY_COMMANDS:
        lines.append(f"- `{command}`")
    lines.extend([
        "",
        "## 금지되는 명령 계열",
        "",
    ])
    for keyword in _BLOCKED_COMMAND_KEYWORDS:
        lines.append(f"- `{keyword}`")
    lines.extend([
        "",
        "## Wizard 단계",
        "",
    ])
    for idx, step in enumerate(pack.get("wizard_steps", []), start=1):
        lines.extend([
            f"### {idx}. {step.get('title')}",
            "",
            f"- 해야 할 일: {step.get('operator_action')}",
            f"- 기대 결과: {step.get('expected_result')}",
            f"- 실행 권한 발생: `{step.get('executes_runtime')}`",
            "",
        ])
    lines.extend([
        "## 실패 메시지 해석",
        "",
    ])
    for item in pack.get("failure_lookup", []):
        lines.extend([
            f"- `{item.get('message_contains')}`: {item.get('meaning')}",
            f"  - 조치: {item.get('operator_action')}",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _build_checklist_markdown(pack: Mapping[str, Any]) -> str:
    checklist = pack.get("operator_checklist", [])
    lines = [
        "# P36 Operator ZIP Drop-in Checklist",
        "",
        "운영자는 아래 항목을 체크한 뒤에도 실행 명령을 누르지 않습니다.",
        "",
    ]
    for item in checklist:
        lines.append(f"- [ ] {item}")
    return "\n".join(lines).rstrip() + "\n"


def _build_failure_lookup_markdown(pack: Mapping[str, Any]) -> str:
    lines = ["# P36 Failure Message Lookup", ""]
    for item in pack.get("failure_lookup", []):
        lines.extend([
            f"## `{item.get('message_contains')}`",
            "",
            f"의미: {item.get('meaning')}",
            "",
            f"운영자 조치: {item.get('operator_action')}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _build_quick_card(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "card_id": "p36_non_developer_onboarding_card",
        "title": "Crypto_AI_System Onboarding Wizard",
        "decision": pack.get("operator_final_activation_decision"),
        "status": pack.get("status"),
        "runtime": "DISABLED",
        "scheduler": "DISABLED",
        "orders": "DISABLED",
        "allowed_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_BLOCKED_COMMAND_KEYWORDS),
        "authority": "REVIEW_ONLY",
        "runtime_authority": False,
        "operator_next_action": "Use status/matrix/waiting/no_go/export_paths only.",
    }


def build_non_developer_onboarding_wizard_report(
    *,
    root: str | Path | None = None,
    p35_report: Mapping[str, Any] | None = None,
    p35_summary: Mapping[str, Any] | None = None,
    p35_pack: Mapping[str, Any] | None = None,
    p35_runbook: str | None = None,
    p35_checklist: str | None = None,
    p35_safe_command_guide: str | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Any]] = (),
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    latest = _latest_dir(cfg)

    missing_artifacts = [name for name in _REQUIRED_P35_ARTIFACTS if not (latest / name).exists()]
    if p35_report is None:
        p35_report = _read_latest_json(cfg, "p35_operator_ux_quickstart_runbook_pack_report.json")
    if p35_summary is None:
        p35_summary = _read_latest_json(cfg, "p35_operator_ux_quickstart_runbook_pack_summary.json")
    if p35_pack is None:
        loaded = _read_latest_json(cfg, "p35_operator_ux_quickstart_runbook_pack.json")
        p35_pack = loaded if isinstance(loaded, Mapping) else {}
    if p35_runbook is None:
        p35_runbook = _read_latest_text(cfg, "p35_operator_ux_quickstart_runbook.md")
    if p35_checklist is None:
        p35_checklist = _read_latest_text(cfg, "p35_operator_ux_checklist.md")
    if p35_safe_command_guide is None:
        p35_safe_command_guide = _read_latest_text(cfg, "p35_safe_command_guide.md")

    payloads: list[tuple[str, Any]] = [
        ("p35_report", dict(p35_report)),
        ("p35_summary", dict(p35_summary)),
        ("p35_pack", dict(p35_pack)),
        ("p35_runbook", p35_runbook),
        ("p35_checklist", p35_checklist),
        ("p35_safe_command_guide", p35_safe_command_guide),
        *list(extra_payloads_for_scan),
    ]
    unsafe_hits = _scan_truthy_execution_fields(payloads)
    secret_hits = _scan_secret_value_patterns(payloads)

    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    p35_status = str(p35_report.get("status", "")) if isinstance(p35_report, Mapping) else ""
    if missing_artifacts:
        waiting_reasons.append("P36_SOURCE_P35_ARTIFACTS_MISSING")
    if not p35_report:
        waiting_reasons.append("P36_SOURCE_P35_REPORT_MISSING")
    if p35_status == P35_STATUS_WAITING_REVIEW_ONLY or _bool(p35_report.get("waiting")):
        waiting_reasons.append("P36_SOURCE_P35_WAITING")
    if p35_status != P35_STATUS_GENERATED_REVIEW_ONLY:
        waiting_reasons.append("P36_SOURCE_P35_NOT_GENERATED")
    if p35_status == P35_STATUS_BLOCKED_FAIL_CLOSED or _bool(p35_report.get("blocked")):
        block_reasons.append("P36_SOURCE_P35_BLOCKED")
    if unsafe_hits:
        block_reasons.append("P36_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P36_SECRET_VALUE_PATTERN_FOUND")

    wizard_steps = _build_wizard_steps()
    failure_lookup = _failure_lookup()
    operator_checklist = [
        "ZIP 파일명이 Crypto_AI_System 패키지인지 확인했다.",
        "압축 해제 후 README.md, scripts, src, storage 폴더가 보이는지 확인했다.",
        "status/matrix/waiting/no_go/export_paths만 조회한다.",
        "enable/start/submit/order/live/trade/activate/scheduler/place/cancel/runtime 계열 명령은 실행하지 않는다.",
        "API key, API secret, private key, passphrase, secret file을 입력하지 않는다.",
        "Runtime: DISABLED, Scheduler: DISABLED, Orders: DISABLED가 정상 상태임을 이해했다.",
        "WAITING은 외부/operator evidence가 부족하다는 뜻이며 실행 허가가 아님을 이해했다.",
        "No-Go가 있으면 다음 단계로 가지 않는다.",
        "review-only 산출물은 runtime authority가 아님을 이해했다.",
        "문제가 발생하면 failure lookup을 먼저 확인한다.",
    ]

    status = STATUS_GENERATED_REVIEW_ONLY
    if waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    if block_reasons:
        status = STATUS_BLOCKED_FAIL_CLOSED

    pack: dict[str, Any] = {
        "version": P36_NON_DEVELOPER_ONBOARDING_WIZARD_VERSION,
        "status": status,
        "waiting": bool(waiting_reasons) and not block_reasons,
        "blocked": bool(block_reasons),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "block_reasons": sorted(set(block_reasons)),
        "created_at_utc": utc_now_canonical(),
        "source_p35_status": p35_status or None,
        "source_p35_report_sha256": sha256_json(p35_report) if p35_report else None,
        "source_p35_pack_sha256": sha256_json(p35_pack) if p35_pack else None,
        "operator_final_activation_decision": p35_pack.get("operator_final_activation_decision") or p35_report.get("operator_final_activation_decision") or "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "allowed_read_only_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "blocked_command_keywords": list(_BLOCKED_COMMAND_KEYWORDS),
        "wizard_steps": wizard_steps,
        "wizard_step_count": len(wizard_steps),
        "failure_lookup": failure_lookup,
        "failure_lookup_count": len(failure_lookup),
        "operator_checklist": operator_checklist,
        "operator_checklist_item_count": len(operator_checklist),
        "missing_required_p35_artifacts": missing_artifacts,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "unsafe_truthy_execution_flag_hit_count": len(unsafe_hits),
        "secret_value_pattern_hits": secret_hits,
        "secret_value_pattern_hit_count": len(secret_hits),
        "all_wizard_artifacts_safe_review_only": not block_reasons,
        "runtime_authority": False,
        "wizard_executes_runtime": False,
        "wizard_enables_scheduler": False,
        "wizard_allows_order_submission": False,
        "wizard_calls_endpoint": False,
        "wizard_reads_secret_value": False,
        "drop_in_guide_enables_runtime": False,
        "drop_in_guide_allows_order_submission": False,
        "failure_lookup_allows_runtime": False,
        "operator_onboarding_card_allows_runtime": False,
        **{key: False for key in _EXECUTION_FIELDS_FOR_P36 if key not in {"wizard_executes_runtime", "wizard_enables_scheduler", "wizard_allows_order_submission", "wizard_calls_endpoint", "wizard_reads_secret_value", "drop_in_guide_enables_runtime", "drop_in_guide_allows_order_submission", "failure_lookup_allows_runtime", "operator_onboarding_card_allows_runtime"}},
        "execution_flags": default_execution_flag_state(),
        "truthy_default_execution_flags": truthy_execution_flags(default_execution_flag_state()),
    }
    pack["zip_drop_in_markdown"] = _build_zip_drop_in_markdown(pack)
    pack["checklist_markdown"] = _build_checklist_markdown(pack)
    pack["failure_lookup_markdown"] = _build_failure_lookup_markdown(pack)
    pack["operator_onboarding_card"] = _build_quick_card(pack)
    pack["report_id"] = stable_id("p36_onboarding_wizard", pack)
    return pack


def build_p36_negative_fixture_results(*, root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else Path.cwd())
    base_report = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
    }
    base_summary = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "blocked": False,
        "waiting": False,
        "all_quickstart_artifacts_safe_review_only": True,
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    base_pack = {
        "status": P35_STATUS_GENERATED_REVIEW_ONLY,
        "operator_final_activation_decision": "WAITING_FOR_REQUIRED_EXTERNAL_OR_OPERATOR_EVIDENCE",
        "safe_commands": list(_ALLOWED_READ_ONLY_COMMANDS),
        "quickstart_executes_runtime": False,
        "quickstart_allows_order_submission": False,
    }
    text = "Runtime: DISABLED\nScheduler: DISABLED\nOrders: DISABLED\n"
    fixtures: dict[str, dict[str, Any]] = {}
    cases: dict[str, dict[str, Any]] = {
        "missing_p35_report": {"p35_report": {}},
        "p35_blocked": {"p35_report": {**base_report, "status": P35_STATUS_BLOCKED_FAIL_CLOSED, "blocked": True}},
        "unsafe_runtime_flag": {"p35_report": {**base_report, "live_scaled_execution_enabled": True}},
        "scheduler_enabled": {"p35_summary": {**base_summary, "runtime_scheduler_enabled": True}},
        "endpoint_called": {"p35_report": {**base_report, "order_endpoint_called": True}},
        "secret_pattern_found": {"p35_runbook": "BINANCE_API_SECRET=leak"},
        "wizard_executes_runtime": {"extra_payloads_for_scan": [("bad_wizard", {"wizard_executes_runtime": True})]},
        "drop_in_allows_order_submission": {"extra_payloads_for_scan": [("bad_drop_in", {"drop_in_guide_allows_order_submission": True})]},
    }
    for case, overrides in cases.items():
        report = build_non_developer_onboarding_wizard_report(
            root=cfg.root,
            p35_report=overrides.get("p35_report", base_report),
            p35_summary=overrides.get("p35_summary", base_summary),
            p35_pack=overrides.get("p35_pack", base_pack),
            p35_runbook=overrides.get("p35_runbook", text),
            p35_checklist=overrides.get("p35_checklist", text),
            p35_safe_command_guide=overrides.get("p35_safe_command_guide", text),
            extra_payloads_for_scan=overrides.get("extra_payloads_for_scan", ()),
        )
        fixtures[case] = {
            "status": report["status"],
            "blocked": bool(report["blocked"]),
            "waiting": bool(report["waiting"]),
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
        }
    all_safe = all(item["blocked"] or item["waiting"] for item in fixtures.values())
    return {
        "status": "P36_NEGATIVE_FIXTURES_RECORDED",
        "fixture_results": fixtures,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all_safe,
        "created_at_utc": utc_now_canonical(),
    }


def persist_non_developer_onboarding_wizard(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p36_non_developer_onboarding_wizard")
    report = build_non_developer_onboarding_wizard_report(root=cfg.root)
    negative = build_p36_negative_fixture_results(root=cfg.root)

    report_path = latest / "p36_non_developer_onboarding_wizard_report.json"
    summary_path = latest / "p36_non_developer_onboarding_wizard_summary.json"
    pack_path = latest / "p36_non_developer_onboarding_wizard_pack.json"
    steps_path = latest / "p36_onboarding_wizard_steps.json"
    markdown_path = latest / "p36_zip_drop_in_wizard.md"
    checklist_path = latest / "p36_zip_drop_in_checklist.md"
    failure_path = latest / "p36_failure_message_lookup.md"
    card_path = latest / "p36_operator_onboarding_card.json"
    negative_path = latest / "p36_non_developer_onboarding_wizard_negative_fixture_results.json"
    registry_record_path = latest / "p36_non_developer_onboarding_wizard_registry_record.json"

    atomic_write_json(report_path, report)
    summary = {
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "operator_final_activation_decision": report["operator_final_activation_decision"],
        "wizard_step_count": report["wizard_step_count"],
        "failure_lookup_count": report["failure_lookup_count"],
        "operator_checklist_item_count": report["operator_checklist_item_count"],
        "allowed_read_only_commands": report["allowed_read_only_commands"],
        "blocked_command_keywords": report["blocked_command_keywords"],
        "all_wizard_artifacts_safe_review_only": report["all_wizard_artifacts_safe_review_only"],
        "runtime_scheduler_enabled": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "onboarding_paths": {
            "wizard_markdown": str(markdown_path),
            "checklist_markdown": str(checklist_path),
            "failure_lookup_markdown": str(failure_path),
            "operator_card": str(card_path),
            "wizard_steps": str(steps_path),
        },
    }
    atomic_write_json(summary_path, summary)
    atomic_write_json(pack_path, {k: v for k, v in report.items() if k not in {"zip_drop_in_markdown", "checklist_markdown", "failure_lookup_markdown"}})
    atomic_write_json(steps_path, report["wizard_steps"])
    _atomic_write_text(markdown_path, report["zip_drop_in_markdown"])
    _atomic_write_text(checklist_path, report["checklist_markdown"])
    _atomic_write_text(failure_path, report["failure_lookup_markdown"])
    atomic_write_json(card_path, report["operator_onboarding_card"])
    atomic_write_json(negative_path, negative)

    atomic_write_json(storage / report_path.name, report)
    atomic_write_json(storage / summary_path.name, summary)
    atomic_write_json(storage / pack_path.name, {k: v for k, v in report.items() if k not in {"zip_drop_in_markdown", "checklist_markdown", "failure_lookup_markdown"}})
    _atomic_write_text(storage / markdown_path.name, report["zip_drop_in_markdown"])
    _atomic_write_text(storage / checklist_path.name, report["checklist_markdown"])
    _atomic_write_text(storage / failure_path.name, report["failure_lookup_markdown"])
    atomic_write_json(storage / card_path.name, report["operator_onboarding_card"])

    registry_record = {
        "registry_record_id": stable_id("p36_registry_record", report),
        "report_id": report["report_id"],
        "status": report["status"],
        "waiting": report["waiting"],
        "blocked": report["blocked"],
        "wizard_step_count": report["wizard_step_count"],
        "allowed_read_only_commands": report["allowed_read_only_commands"],
        "runtime_scheduler_enabled": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    atomic_write_json(registry_record_path, registry_record)
    append_registry_record(
        registry_path(cfg, P36_NON_DEVELOPER_ONBOARDING_WIZARD_REGISTRY_NAME),
        registry_record,
        registry_name=P36_NON_DEVELOPER_ONBOARDING_WIZARD_REGISTRY_NAME,
    )
    return report


__all__ = [
    "P36_NON_DEVELOPER_ONBOARDING_WIZARD_VERSION",
    "STATUS_GENERATED_REVIEW_ONLY",
    "STATUS_WAITING_REVIEW_ONLY",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "build_non_developer_onboarding_wizard_report",
    "build_p36_negative_fixture_results",
    "persist_non_developer_onboarding_wizard",
]
