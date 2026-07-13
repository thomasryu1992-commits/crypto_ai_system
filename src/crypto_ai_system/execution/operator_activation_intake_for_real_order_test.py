from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, sha256_text, utc_now_canonical


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: str | Path, data: Any) -> None:
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


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str) + "\n")


P66_VERSION = "p66_operator_activation_intake_for_real_order_test_v1"
STATUS_P66_READY = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_READY_REVIEW_ONLY_NO_CALL"
STATUS_P66_ACCEPTED = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_ACCEPTED_REVIEW_ONLY_NO_CALL"
STATUS_P66_BLOCKED = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_BLOCKED_FAIL_CLOSED"
P66_TEMPLATE_SCOPE = "p66_operator_activation_intake_template_only"
P65_APPROVED_ORDER_TEST_SCOPE = "p65_approved_testnet_order_test_only"
P65_SOURCE_STATUS = "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_VALIDATED_REVIEW_ONLY_DISABLED"
EXACT_P65_OPERATOR_PHRASE = "AUTHORIZE ONE P65 BINANCE FUTURES TESTNET ORDER TEST SENDER EXECUTABLE RUN ONLY"
ALLOWED_VENUE = "binance_futures_testnet"
ALLOWED_BASE_URL = "https://demo-fapi.binance.com"
ALLOWED_METHOD = "POST"
ALLOWED_PATH = "/fapi/v1/order/test"
ALLOWED_SYMBOL = "BTCUSDT"
MAX_INTAKE_VALIDITY_SECONDS = 900
P66_REGISTRY_NAME = "p66_operator_activation_intake_for_real_order_test_registry"

FORBIDDEN_KEY_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_secret",
    "credential_value",
    "secret_file_contents",
    "raw_signed_payload",
    "raw_request_body",
    "raw_response_body",
    "authorization_header",
    "x-mbx-apikey",
)
FORBIDDEN_VALUE_TOKENS = (
    "-----BEGIN PRIVATE KEY-----",
    "api_secret=",
    "api_key=",
    "x-mbx-apikey:",
    "authorization: bearer ",
)


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _is_nonzero_sha256(value: Any) -> bool:
    return _is_sha256(value) and str(value).lower() != "0" * 64


def _walk_forbidden(obj: Any, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            lower = str(key).lower()
            if not isinstance(value, bool) and any(token in lower for token in FORBIDDEN_KEY_TOKENS):
                blockers.append(f"P66_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        lower = obj.lower()
        if any(token.lower() in lower for token in FORBIDDEN_VALUE_TOKENS):
            blockers.append(f"P66_FORBIDDEN_SECRET_OR_RAW_VALUE:{prefix or '<root>'}")
    return blockers


def _parse_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _canonical_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _without_hash(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != hash_field}


def _expected_nested_hash(payload: Mapping[str, Any], hash_field: str) -> str:
    return sha256_json(_without_hash(payload, hash_field))


@dataclass(frozen=True)
class P66OperatorActivationIntake:
    intake_version: str = P66_VERSION
    artifact_type: str = "p66_operator_activation_intake"
    operator_request_id: str = "FILL_OPERATOR_REQUEST_ID"
    operator_phrase: str = EXACT_P65_OPERATOR_PHRASE
    approval_granted: bool = False
    actual_operator_supplied: bool = False
    fixture_only: bool = False
    execution_scope: str = P66_TEMPLATE_SCOPE
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_BASE_URL
    method: str = ALLOWED_METHOD
    path: str = ALLOWED_PATH
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    redacted_evidence_only: bool = True
    process_memory_credentials_only: bool = True
    credential_reference_id: str = "FILL_METADATA_ONLY_CREDENTIAL_REFERENCE"
    key_fingerprint_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64
    operator_confirmation_sha256: str = "0" * 64
    p65_report_sha256: str = "0" * 64
    p65_policy_sha256: str = "0" * 64
    p65_activation_template_sha256: str = "0" * 64
    p65_order_test_intent_sha256: str = "0" * 64
    created_at_utc: str = "1970-01-01T00:00:00Z"
    expires_at_utc: str = "1970-01-01T00:15:00Z"
    real_order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    runtime_authority_granted: bool = False
    live_execution_allowed: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["operator_confirmation_sha256"] == "0" * 64:
            payload["operator_confirmation_sha256"] = sha256_text(self.operator_phrase)
        payload["p66_operator_activation_intake_sha256"] = sha256_json(payload)
        return payload


def validate_p65_source_report(report: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _walk_forbidden(report)
    if report.get("status") != P65_SOURCE_STATUS:
        blockers.append("P66_P65_SOURCE_STATUS_INVALID")
    source_hash = str(report.get("p65_operator_installed_testnet_sender_executable_sha256", ""))
    if not _is_sha256(source_hash):
        blockers.append("P66_P65_SOURCE_HASH_INVALID")
    elif source_hash != _expected_nested_hash(report, "p65_operator_installed_testnet_sender_executable_sha256"):
        blockers.append("P66_P65_SOURCE_HASH_MISMATCH")
    if report.get("review_only") is not True:
        blockers.append("P66_P65_SOURCE_REVIEW_ONLY_REQUIRED")
    for key in (
        "external_sender_executable_enabled",
        "real_order_test_endpoint_call_enabled",
        "real_order_test_endpoint_call_performed",
        "real_order_endpoint_enabled",
        "real_order_endpoint_called",
        "actual_order_submission_performed",
        "actual_testnet_order_submitted",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "runtime_mutation_performed",
    ):
        if report.get(key) is not False:
            blockers.append(f"P66_P65_SOURCE_EXPECTED_FALSE:{key}")
    if report.get("no_network_sender_executable_self_test_passed") is not True:
        blockers.append("P66_P65_SOURCE_SELF_TEST_NOT_PASSED")
    if report.get("negative_fixtures_all_blocked") is not True:
        blockers.append("P66_P65_SOURCE_NEGATIVE_FIXTURES_NOT_BLOCKED")

    policy = report.get("policy") if isinstance(report.get("policy"), Mapping) else {}
    activation = report.get("operator_activation_template") if isinstance(report.get("operator_activation_template"), Mapping) else {}
    intent = report.get("order_test_intent_template") if isinstance(report.get("order_test_intent_template"), Mapping) else {}
    if policy.get("base_url") != ALLOWED_BASE_URL or policy.get("path") != ALLOWED_PATH or policy.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P66_P65_SOURCE_POLICY_SCOPE_INVALID")
    if policy.get("executable_enabled") is not False or policy.get("order_test_call_enabled") is not False:
        blockers.append("P66_P65_SOURCE_POLICY_NOT_DISABLED")
    if activation.get("approval_granted") is not False or activation.get("runtime_authority_granted") is not False:
        blockers.append("P66_P65_SOURCE_ACTIVATION_TEMPLATE_UNSAFE")
    if intent.get("base_url") != ALLOWED_BASE_URL or intent.get("path") != ALLOWED_PATH or intent.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P66_P65_SOURCE_INTENT_SCOPE_INVALID")
    if intent.get("order_submit_allowed") is not False:
        blockers.append("P66_P65_SOURCE_INTENT_ORDER_SUBMIT_ALLOWED")
    return {
        "p65_source_valid": not blockers,
        "p65_source_block_reasons": sorted(set(blockers)),
        "p65_source_sha256": source_hash,
    }


def build_p66_operator_activation_intake_template(
    p65_report: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    policy = p65_report.get("policy") if isinstance(p65_report.get("policy"), Mapping) else {}
    activation = p65_report.get("operator_activation_template") if isinstance(p65_report.get("operator_activation_template"), Mapping) else {}
    intent = p65_report.get("order_test_intent_template") if isinstance(p65_report.get("order_test_intent_template"), Mapping) else {}
    return P66OperatorActivationIntake(
        p65_report_sha256=str(p65_report.get("p65_operator_installed_testnet_sender_executable_sha256", "0" * 64)),
        p65_policy_sha256=str(policy.get("p65_sender_executable_policy_sha256", "0" * 64)),
        p65_activation_template_sha256=str(activation.get("p65_operator_activation_sha256", "0" * 64)),
        p65_order_test_intent_sha256=str(intent.get("p65_order_test_intent_sha256", "0" * 64)),
        created_at_utc=_canonical_utc(now),
        expires_at_utc=_canonical_utc(now + timedelta(seconds=MAX_INTAKE_VALIDITY_SECONDS)),
    ).to_dict()


def build_valid_p66_operator_activation_intake_fixture(
    p65_report: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    template = build_p66_operator_activation_intake_template(p65_report, now=now)
    payload = dict(template)
    payload.pop("p66_operator_activation_intake_sha256", None)
    payload.update(
        {
            "operator_request_id": "p66-valid-operator-fixture",
            "approval_granted": True,
            "actual_operator_supplied": True,
            "fixture_only": True,
            "execution_scope": P65_APPROVED_ORDER_TEST_SCOPE,
            "credential_reference_id": "metadata-only:operator-os-provider:binance-futures-testnet",
            "key_fingerprint_sha256": "c" * 64,
            "one_shot_nonce_sha256": "d" * 64,
            "created_at_utc": _canonical_utc(now),
            "expires_at_utc": _canonical_utc(now + timedelta(minutes=10)),
        }
    )
    payload["operator_confirmation_sha256"] = sha256_text(EXACT_P65_OPERATOR_PHRASE)
    payload["p66_operator_activation_intake_sha256"] = sha256_json(payload)
    return payload


def validate_p66_operator_activation_intake(
    intake: Mapping[str, Any],
    p65_report: Mapping[str, Any],
    *,
    require_approved: bool,
    allow_fixture: bool = False,
    seen_nonce_hashes: Iterable[str] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    blockers = _walk_forbidden(intake)
    source = validate_p65_source_report(p65_report)
    blockers.extend(source["p65_source_block_reasons"])

    if intake.get("operator_phrase") != EXACT_P65_OPERATOR_PHRASE:
        blockers.append("P66_OPERATOR_PHRASE_MISMATCH")
    if intake.get("operator_confirmation_sha256") != sha256_text(EXACT_P65_OPERATOR_PHRASE):
        blockers.append("P66_OPERATOR_CONFIRMATION_HASH_MISMATCH")
    if intake.get("p65_report_sha256") != source.get("p65_source_sha256"):
        blockers.append("P66_P65_REPORT_HASH_BINDING_MISMATCH")

    policy = p65_report.get("policy") if isinstance(p65_report.get("policy"), Mapping) else {}
    activation = p65_report.get("operator_activation_template") if isinstance(p65_report.get("operator_activation_template"), Mapping) else {}
    intent = p65_report.get("order_test_intent_template") if isinstance(p65_report.get("order_test_intent_template"), Mapping) else {}
    expected_bindings = {
        "p65_policy_sha256": policy.get("p65_sender_executable_policy_sha256"),
        "p65_activation_template_sha256": activation.get("p65_operator_activation_sha256"),
        "p65_order_test_intent_sha256": intent.get("p65_order_test_intent_sha256"),
    }
    for key, expected in expected_bindings.items():
        if intake.get(key) != expected:
            blockers.append(f"P66_SOURCE_BINDING_MISMATCH:{key}")

    if intake.get("venue") != ALLOWED_VENUE:
        blockers.append("P66_VENUE_NOT_ALLOWED")
    if intake.get("base_url") != ALLOWED_BASE_URL:
        blockers.append("P66_BASE_URL_NOT_TESTNET")
    if intake.get("method") != ALLOWED_METHOD:
        blockers.append("P66_METHOD_NOT_POST")
    if intake.get("path") != ALLOWED_PATH:
        blockers.append("P66_PATH_NOT_ORDER_TEST")
    if intake.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P66_SYMBOL_NOT_ALLOWED")
    if intake.get("max_call_count") != 1:
        blockers.append("P66_MAX_CALL_COUNT_MUST_BE_ONE")
    for key in ("testnet_only", "order_test_only", "one_request_only", "redacted_evidence_only", "process_memory_credentials_only"):
        if intake.get(key) is not True:
            blockers.append(f"P66_EXPECTED_TRUE:{key}")
    for key in (
        "real_order_submit_allowed",
        "status_polling_allowed",
        "cancel_allowed",
        "runtime_authority_granted",
        "live_execution_allowed",
        "auto_promotion_allowed",
    ):
        if intake.get(key) is not False:
            blockers.append(f"P66_EXPECTED_FALSE:{key}")

    intake_hash = str(intake.get("p66_operator_activation_intake_sha256", ""))
    if not _is_sha256(intake_hash):
        blockers.append("P66_INTAKE_HASH_INVALID")
    elif intake_hash != _expected_nested_hash(intake, "p66_operator_activation_intake_sha256"):
        blockers.append("P66_INTAKE_HASH_MISMATCH")

    if require_approved:
        if intake.get("approval_granted") is not True:
            blockers.append("P66_APPROVAL_NOT_GRANTED")
        if intake.get("actual_operator_supplied") is not True:
            blockers.append("P66_ACTUAL_OPERATOR_SUPPLIED_REQUIRED")
        if intake.get("execution_scope") != P65_APPROVED_ORDER_TEST_SCOPE:
            blockers.append("P66_APPROVED_SCOPE_REQUIRED")
        if intake.get("fixture_only") is True and not allow_fixture:
            blockers.append("P66_FIXTURE_NOT_ALLOWED_FOR_ACTUAL_INTAKE")
        credential_ref = str(intake.get("credential_reference_id", "")).strip()
        if not credential_ref or credential_ref.startswith("FILL_"):
            blockers.append("P66_CREDENTIAL_REFERENCE_REQUIRED")
        if not _is_nonzero_sha256(intake.get("key_fingerprint_sha256")):
            blockers.append("P66_KEY_FINGERPRINT_REQUIRED")
        nonce = str(intake.get("one_shot_nonce_sha256", ""))
        if not _is_nonzero_sha256(nonce):
            blockers.append("P66_ONE_SHOT_NONCE_REQUIRED")
        if nonce in {str(value) for value in seen_nonce_hashes}:
            blockers.append("P66_ONE_SHOT_NONCE_ALREADY_SEEN")

        created = _parse_utc(intake.get("created_at_utc"))
        expires = _parse_utc(intake.get("expires_at_utc"))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        if created is None:
            blockers.append("P66_CREATED_AT_INVALID")
        if expires is None:
            blockers.append("P66_EXPIRES_AT_INVALID")
        if created is not None and expires is not None:
            validity = int((expires - created).total_seconds())
            if validity <= 0 or validity > MAX_INTAKE_VALIDITY_SECONDS:
                blockers.append("P66_VALIDITY_WINDOW_INVALID")
            if current < created:
                blockers.append("P66_INTAKE_NOT_YET_VALID")
            if current > expires:
                blockers.append("P66_INTAKE_EXPIRED")
    else:
        if intake.get("approval_granted") is not False:
            blockers.append("P66_TEMPLATE_APPROVAL_MUST_BE_FALSE")
        if intake.get("actual_operator_supplied") is not False:
            blockers.append("P66_TEMPLATE_OPERATOR_SUPPLIED_MUST_BE_FALSE")
        if intake.get("fixture_only") is not False:
            blockers.append("P66_TEMPLATE_FIXTURE_ONLY_MUST_BE_FALSE")
        if intake.get("execution_scope") != P66_TEMPLATE_SCOPE:
            blockers.append("P66_TEMPLATE_SCOPE_INVALID")

    blockers = sorted(set(blockers))
    return {
        "status": STATUS_P66_ACCEPTED if require_approved and not blockers else (STATUS_P66_READY if not blockers else STATUS_P66_BLOCKED),
        "p66_operator_activation_intake_valid": not blockers,
        "p66_operator_activation_intake_block_reasons": blockers,
        "require_approved": require_approved,
        "allow_fixture": allow_fixture,
        "operator_activation_intake_accepted": require_approved and not blockers,
        "eligible_for_separate_external_order_test_execution_step": require_approved and not blockers,
        "real_order_test_execution_enabled": False,
        "real_order_test_execution_performed": False,
        "runtime_authority_granted": False,
        "actual_order_submission_performed": False,
    }


def build_p66_activation_validation_receipt(
    intake: Mapping[str, Any], validation: Mapping[str, Any], *, fixture_validation_only: bool
) -> dict[str, Any]:
    accepted = validation.get("p66_operator_activation_intake_valid") is True and validation.get("require_approved") is True
    receipt = {
        "artifact_type": "p66_operator_activation_intake_validation_receipt",
        "status": STATUS_P66_ACCEPTED if accepted else STATUS_P66_BLOCKED,
        "accepted": accepted,
        "blocked": not accepted,
        "review_only": True,
        "fixture_validation_only": fixture_validation_only,
        "operator_activation_intake_sha256": intake.get("p66_operator_activation_intake_sha256"),
        "operator_request_id": intake.get("operator_request_id"),
        "one_shot_nonce_sha256": intake.get("one_shot_nonce_sha256"),
        "key_fingerprint_sha256": intake.get("key_fingerprint_sha256"),
        "eligible_for_separate_external_order_test_execution_step": accepted and not fixture_validation_only,
        "activation_intake_recorded_by_p66": False,
        "one_shot_nonce_consumed_by_p66": False,
        "sender_executable_enabled_by_p66": False,
        "real_order_test_execution_enabled_by_p66": False,
        "real_order_test_execution_performed_by_p66": False,
        "http_request_sent_by_p66": False,
        "signature_created_by_p66": False,
        "secret_value_accessed_by_p66": False,
        "actual_order_submission_performed_by_p66": False,
        "runtime_mutation_performed_by_p66": False,
        "block_reasons": list(validation.get("p66_operator_activation_intake_block_reasons", [])),
    }
    receipt["p66_activation_validation_receipt_sha256"] = sha256_json(receipt)
    return receipt


def build_p66_negative_fixture_results(p65_report: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    valid = build_valid_p66_operator_activation_intake_fixture(p65_report, now=now)
    cases: list[tuple[str, dict[str, Any], set[str], datetime | None]] = []

    def mutated(**updates: Any) -> dict[str, Any]:
        payload = dict(valid)
        payload.pop("p66_operator_activation_intake_sha256", None)
        payload.update(updates)
        payload["p66_operator_activation_intake_sha256"] = sha256_json(payload)
        return payload

    cases.extend(
        [
            ("bad_operator_phrase", mutated(operator_phrase="BAD", operator_confirmation_sha256="0" * 64), set(), now),
            ("approval_not_granted", mutated(approval_granted=False), set(), now),
            ("wrong_execution_scope", mutated(execution_scope="wrong"), set(), now),
            ("mainnet_base_url", mutated(base_url="https://fapi.binance.com"), set(), now),
            ("real_order_submit_path", mutated(path="/fapi/v1/order"), set(), now),
            ("wrong_symbol", mutated(symbol="ETHUSDT"), set(), now),
            ("raw_api_secret_field", {**mutated(), "api_secret_value": "forbidden"}, set(), now),
            ("invalid_key_fingerprint", mutated(key_fingerprint_sha256="bad"), set(), now),
            ("zero_nonce", mutated(one_shot_nonce_sha256="0" * 64), set(), now),
            ("expired_intake", mutated(created_at_utc=_canonical_utc(now - timedelta(minutes=20)), expires_at_utc=_canonical_utc(now - timedelta(minutes=5))), set(), now),
            ("duplicate_nonce", mutated(), {str(valid["one_shot_nonce_sha256"])}, now),
            ("runtime_authority_requested", mutated(runtime_authority_granted=True), set(), now),
        ]
    )
    results = []
    for name, payload, seen, check_now in cases:
        result = validate_p66_operator_activation_intake(
            payload,
            p65_report,
            require_approved=True,
            allow_fixture=True,
            seen_nonce_hashes=seen,
            now=check_now,
        )
        results.append({
            "case": name,
            "blocked": result["p66_operator_activation_intake_valid"] is False,
            "block_reasons": result["p66_operator_activation_intake_block_reasons"],
        })
    return {
        "artifact_type": "p66_operator_activation_intake_negative_fixture_results",
        "case_count": len(results),
        "cases": results,
        "all_negative_fixtures_blocked": all(item["blocked"] for item in results),
    }


def build_p66_operator_activation_intake_report(
    p65_report: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    source_validation = validate_p65_source_report(p65_report)
    template = build_p66_operator_activation_intake_template(p65_report, now=now)
    template_validation = validate_p66_operator_activation_intake(
        template, p65_report, require_approved=False, now=now
    )
    fixture = build_valid_p66_operator_activation_intake_fixture(p65_report, now=now)
    fixture_validation = validate_p66_operator_activation_intake(
        fixture, p65_report, require_approved=True, allow_fixture=True, now=now
    )
    fixture_receipt = build_p66_activation_validation_receipt(
        fixture, fixture_validation, fixture_validation_only=True
    )
    negative = build_p66_negative_fixture_results(p65_report, now=now)
    ready = (
        source_validation["p65_source_valid"]
        and template_validation["p66_operator_activation_intake_valid"]
        and fixture_validation["p66_operator_activation_intake_valid"]
        and negative["all_negative_fixtures_blocked"]
    )
    report = {
        "artifact_type": "p66_operator_activation_intake_for_real_order_test_report",
        "status": STATUS_P66_READY if ready else STATUS_P66_BLOCKED,
        "blocked": not ready,
        "review_only": True,
        "runtime_authority_source": False,
        "p66_operator_activation_intake_validator_implemented": True,
        "p65_source_valid": source_validation["p65_source_valid"],
        "operator_activation_intake_template_created": True,
        "approved_fixture_validation_passed": fixture_validation["p66_operator_activation_intake_valid"],
        "approved_fixture_receipt_created": fixture_receipt["accepted"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked"],
        "actual_operator_activation_received": False,
        "actual_operator_activation_accepted": False,
        "actual_operator_activation_recorded": False,
        "real_order_test_activation_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "sender_executable_enabled": False,
        "one_shot_nonce_consumed": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "actual_live_order_submitted": False,
        "runtime_mutation_performed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "p65_source_validation": source_validation,
        "operator_activation_intake_template": template,
        "approved_fixture_validation": fixture_validation,
        "approved_fixture_receipt": fixture_receipt,
        "negative_fixture_summary": {
            "case_count": negative["case_count"],
            "all_blocked": negative["all_negative_fixtures_blocked"],
        },
    }
    report["p66_operator_activation_intake_for_real_order_test_sha256"] = sha256_json(report)
    return report


def persist_p66_operator_activation_intake_for_real_order_test(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    latest = root / "storage" / "latest"
    phase_dir = root / "storage" / "p66_operator_activation_intake_for_real_order_test"
    registries = root / "storage" / "registries"
    latest.mkdir(parents=True, exist_ok=True)
    phase_dir.mkdir(parents=True, exist_ok=True)
    registries.mkdir(parents=True, exist_ok=True)

    p65_path = latest / "p65_operator_installed_testnet_sender_executable_report.json"
    p65_report = read_json(p65_path)
    if not isinstance(p65_report, dict):
        raise FileNotFoundError(f"Missing P65 source report: {p65_path}")

    report = build_p66_operator_activation_intake_report(p65_report)
    template = report["operator_activation_intake_template"]
    fixture = build_valid_p66_operator_activation_intake_fixture(p65_report)
    fixture_validation = validate_p66_operator_activation_intake(
        fixture, p65_report, require_approved=True, allow_fixture=True
    )
    fixture_receipt = build_p66_activation_validation_receipt(fixture, fixture_validation, fixture_validation_only=True)
    negative = build_p66_negative_fixture_results(p65_report)
    summary = {
        "status": report["status"],
        "review_only": True,
        "actual_operator_activation_received": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
        "secret_value_accessed": False,
        "report_sha256": report["p66_operator_activation_intake_for_real_order_test_sha256"],
    }
    registry_record = {
        "artifact_type": "p66_operator_activation_intake_for_real_order_test_registry_record",
        "status": report["status"],
        "review_only": True,
        "runtime_authority_source": False,
        "report_sha256": report["p66_operator_activation_intake_for_real_order_test_sha256"],
        "actual_operator_activation_received": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "actual_order_submission_performed": False,
        "secret_value_accessed": False,
        "created_at_utc": utc_now_canonical(),
    }
    registry_record["p66_registry_record_sha256"] = sha256_json(registry_record)

    outputs = {
        "p66_operator_activation_intake_for_real_order_test_report.json": report,
        "p66_operator_activation_intake_TEMPLATE_REVIEW_ONLY_NO_CALL.json": template,
        "p66_operator_activation_intake_ACCEPTED_FIXTURE_REVIEW_ONLY_NO_CALL.json": fixture,
        "p66_operator_activation_intake_validation_receipt_FIXTURE_ONLY_NO_CALL.json": fixture_receipt,
        "p66_operator_activation_intake_negative_fixture_results.json": negative,
        "p66_operator_activation_intake_summary.json": summary,
        "p66_operator_activation_intake_registry_record.json": registry_record,
    }
    for filename, payload in outputs.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(phase_dir / filename, payload)

    registry_path = registries / f"{P66_REGISTRY_NAME}.jsonl"
    existing = read_jsonl(registry_path)
    if not any(row.get("report_sha256") == registry_record["report_sha256"] for row in existing):
        append_jsonl(registry_path, registry_record)

    (root / "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_REPORT.md").write_text(
        _markdown_report(report), encoding="utf-8"
    )
    return report


def validate_p66_intake_file(
    intake_path: str | Path,
    p65_report_path: str | Path,
    *,
    seen_nonce_hashes: Iterable[str] = (),
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    intake = read_json(intake_path)
    p65_report = read_json(p65_report_path)
    if not isinstance(intake, dict):
        raise ValueError(f"P66 intake file is not a JSON object: {intake_path}")
    if not isinstance(p65_report, dict):
        raise ValueError(f"P65 source report is not a JSON object: {p65_report_path}")
    validation = validate_p66_operator_activation_intake(
        intake,
        p65_report,
        require_approved=True,
        allow_fixture=False,
        seen_nonce_hashes=seen_nonce_hashes,
        now=now,
    )
    receipt = build_p66_activation_validation_receipt(
        intake, validation, fixture_validation_only=False
    )
    return validation, receipt


def _markdown_report(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# P66 Operator Activation Intake for Real `/fapi/v1/order/test`",
            "",
            f"Status: `{report['status']}`",
            "",
            "P66 implements the operator activation intake validator only. No sender executable is enabled, no nonce is consumed, and no `/fapi/v1/order/test` call is performed.",
            "",
            "Current runtime-impacting flags remain false:",
            "",
            "```text",
            "actual_operator_activation_received=false",
            "real_order_test_activation_enabled=false",
            "real_order_test_endpoint_call_enabled=false",
            "real_order_test_endpoint_call_performed=false",
            "sender_executable_enabled=false",
            "one_shot_nonce_consumed=false",
            "http_request_sent=false",
            "signature_created=false",
            "secret_value_accessed=false",
            "actual_order_submission_performed=false",
            "runtime_mutation_performed=false",
            "```",
            "",
            f"Report SHA256: `{report['p66_operator_activation_intake_for_real_order_test_sha256']}`",
            "",
        ]
    )
