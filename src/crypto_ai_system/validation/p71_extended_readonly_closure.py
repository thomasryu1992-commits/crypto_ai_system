from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from crypto_ai_system.execution.extended_read_only_connectivity import (
    P71_EVIDENCE_MAX_AGE_SECONDS,
    P71_PRIVATE_RECEIPT_VERSION,
    P71_VERSION,
    build_p71_complete_evidence,
)
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P71_CLOSURE_VERSION = "p71_extended_readonly_closure_v1"
P71_CLOSURE_ATTESTATION_VERSION = "p71_extended_readonly_attestation_v1"
P71_CLOSURE_REGISTRY_VERSION = "p71_extended_readonly_consumed_evidence_registry_v1"
P71_MAX_SOURCE_SKEW_SECONDS = 180


class P71ClosureError(RuntimeError):
    pass


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower())


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(dict(payload), indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def _registry_lock(registry_path: Path, *, timeout_seconds: float = 10.0):
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise P71ClosureError(f"Timed out waiting for P71 closure registry lock: {lock_path}")
            time.sleep(0.1)
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_registry_records(path: str | Path) -> list[dict[str, Any]]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(registry_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise P71ClosureError(f"Invalid P71 closure registry JSONL at line {line_number}: {exc}") from exc
        if not isinstance(item, Mapping):
            raise P71ClosureError(f"Invalid P71 closure registry record at line {line_number}")
        record = dict(item)
        expected_hash = record.get("registry_record_sha256")
        without_hash = dict(record)
        without_hash.pop("registry_record_sha256", None)
        if not _is_sha256(expected_hash) or expected_hash != sha256_json(without_hash):
            raise P71ClosureError(f"P71 closure registry hash mismatch at line {line_number}")
        records.append(record)
    return records


def _seen_ids(records: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    public_ids: set[str] = set()
    private_ids: set[str] = set()
    for record in records:
        public_id = str(record.get("public_evidence_id") or "")
        private_id = str(record.get("private_read_session_id") or "")
        if public_id:
            public_ids.add(public_id)
        if private_id:
            private_ids.add(private_id)
    return public_ids, private_ids


def _source_skew_seconds(public_evidence: Mapping[str, Any], private_receipt: Mapping[str, Any]) -> float | None:
    public_time = _parse_utc(public_evidence.get("observed_at_utc"))
    private_time = _parse_utc(private_receipt.get("created_at_utc"))
    if public_time is None or private_time is None:
        return None
    return abs((private_time - public_time).total_seconds())


def _assert_redacted(payload: Mapping[str, Any]) -> None:
    forbidden_keys = {
        "api_key",
        "api_secret",
        "private_key",
        "secret_value",
        "raw_response",
        "endpoint_receipts",
        "account_stream_receipt",
    }

    def walk(value: Any, path: str = "$") -> list[str]:
        matches: list[str] = []
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key).lower()
                if key_text in forbidden_keys:
                    matches.append(f"{path}.{key}")
                matches.extend(walk(child, f"{path}.{key}"))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                matches.extend(walk(child, f"{path}[{index}]"))
        return matches

    matches = walk(payload)
    if matches:
        raise P71ClosureError("Closure output contains forbidden sensitive/raw fields: " + ", ".join(matches))


def _private_rest_valid(private_receipt: Mapping[str, Any]) -> bool:
    endpoints = private_receipt.get("endpoint_receipts") or {}
    required = {"account_info", "balance", "positions", "open_orders"}
    if not isinstance(endpoints, Mapping) or set(endpoints) != required:
        return False
    for name, raw_item in endpoints.items():
        if not isinstance(raw_item, Mapping):
            return False
        if raw_item.get("http_method") != "GET" or raw_item.get("schema_valid") is not True:
            return False
        normal = raw_item.get("http_status") == 200 and raw_item.get("response_status") == "OK"
        zero_balance = name == "balance" and raw_item.get("http_status") == 404 and raw_item.get("zero_balance_confirmed") is True
        if not (normal or zero_balance):
            return False
    return True


def _private_websocket_valid(private_receipt: Mapping[str, Any]) -> bool:
    stream = private_receipt.get("account_stream_receipt") or {}
    if not isinstance(stream, Mapping):
        return False
    return all(
        stream.get(field) is True
        for field in (
            "actual_network_read_performed",
            "initial_snapshot_valid",
            "sequence_valid",
            "heartbeat_policy_valid",
            "heartbeat_window_observed",
            "clock_evidence_valid",
            "market_scope_valid",
            "no_secret_scan_passed",
        )
    )


def build_p71_closure_report(
    *,
    public_evidence: Mapping[str, Any],
    private_receipt: Mapping[str, Any],
    consumed_registry_records: Iterable[Mapping[str, Any]] = (),
    operator_session_id: str | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    records = [dict(item) for item in consumed_registry_records]
    seen_public_ids, seen_private_ids = _seen_ids(records)
    complete_evidence = build_p71_complete_evidence(
        public_evidence=public_evidence,
        private_receipt=private_receipt,
        now_epoch_ms=now_epoch_ms,
        seen_public_evidence_ids=seen_public_ids,
        seen_private_session_ids=seen_private_ids,
    )
    blockers = list(complete_evidence.get("block_reasons") or [])

    public_id = str(public_evidence.get("evidence_id") or "")
    private_session_id = str(private_receipt.get("read_session_id") or "")
    public_hash = str(public_evidence.get("evidence_sha256") or "")
    private_hash = str(private_receipt.get("receipt_sha256") or "")

    if not public_id:
        blockers.append("P71_CLOSURE_PUBLIC_EVIDENCE_ID_MISSING")
    if not private_session_id:
        blockers.append("P71_CLOSURE_PRIVATE_SESSION_ID_MISSING")
    if not _is_sha256(public_hash):
        blockers.append("P71_CLOSURE_PUBLIC_HASH_INVALID")
    if not _is_sha256(private_hash):
        blockers.append("P71_CLOSURE_PRIVATE_HASH_INVALID")

    source_skew = _source_skew_seconds(public_evidence, private_receipt)
    if source_skew is None:
        blockers.append("P71_CLOSURE_SOURCE_TIME_MISSING")
    elif source_skew > P71_MAX_SOURCE_SKEW_SECONDS:
        blockers.append("P71_CLOSURE_SOURCE_TIME_SKEW_EXCEEDED")

    resolved_operator_session_id = str(operator_session_id or f"p71_operator_session_{uuid.uuid4().hex}")
    if not re.fullmatch(r"p71_operator_session_[A-Za-z0-9_-]{1,160}", resolved_operator_session_id):
        blockers.append("P71_CLOSURE_OPERATOR_SESSION_ID_INVALID")

    blockers = sorted(set(str(item) for item in blockers if item))
    closure_complete = complete_evidence.get("p71_complete") is True and not blockers
    created_at = utc_now_canonical()
    closure_id = stable_id(
        "p71_extended_readonly_closure",
        {
            "operator_session_id": resolved_operator_session_id,
            "public_evidence_id": public_id,
            "private_read_session_id": private_session_id,
            "public_evidence_sha256": public_hash,
            "private_receipt_sha256": private_hash,
            "created_at_utc": created_at,
        },
    )
    report: dict[str, Any] = {
        "closure_version": P71_CLOSURE_VERSION,
        "closure_report_id": closure_id,
        "operator_session_id": resolved_operator_session_id,
        "status": "P71_EXTENDED_READONLY_CLOSURE_COMPLETE" if closure_complete else "P71_EXTENDED_READONLY_CLOSURE_BLOCKED",
        "p71_complete": closure_complete,
        "venue": "extended_starknet_sepolia",
        "environment": "testnet",
        "market": "BTC-USD",
        "public_contract_version": P71_VERSION,
        "private_receipt_version": P71_PRIVATE_RECEIPT_VERSION,
        "public_evidence_id": public_id,
        "private_read_session_id": private_session_id,
        "public_evidence_sha256": public_hash,
        "private_receipt_sha256": private_hash,
        "source_time_skew_seconds": source_skew,
        "max_source_time_skew_seconds": P71_MAX_SOURCE_SKEW_SECONDS,
        "evidence_max_age_seconds": P71_EVIDENCE_MAX_AGE_SECONDS,
        "public_rest_valid": complete_evidence.get("public_rest_valid") is True,
        "public_websocket_valid": complete_evidence.get("public_stream_valid") is True,
        "private_account_rest_valid": _private_rest_valid(private_receipt),
        "private_account_websocket_valid": _private_websocket_valid(private_receipt),
        "block_reasons": blockers,
        "source_complete_evidence_sha256": complete_evidence.get("evidence_sha256"),
        "closure_consumes_evidence_on_success": True,
        "closure_evidence_consumed": False,
        "credential_value_present": False,
        "raw_source_payload_included": False,
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "cancel_endpoint_called": False,
        "signature_created": False,
        "stark_private_key_accessed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "created_at_utc": created_at,
    }
    report["closure_report_sha256"] = sha256_json(report)
    _assert_redacted(report)
    return report


def build_p71_redacted_attestation(report: Mapping[str, Any]) -> dict[str, Any]:
    attestation = {
        "attestation_version": P71_CLOSURE_ATTESTATION_VERSION,
        "closure_report_id": report.get("closure_report_id"),
        "closure_report_sha256": report.get("closure_report_sha256"),
        "status": report.get("status"),
        "p71_complete": report.get("p71_complete") is True,
        "venue": report.get("venue"),
        "environment": report.get("environment"),
        "market": report.get("market"),
        "operator_session_id": report.get("operator_session_id"),
        "public_evidence_id": report.get("public_evidence_id"),
        "private_read_session_id": report.get("private_read_session_id"),
        "public_evidence_sha256": report.get("public_evidence_sha256"),
        "private_receipt_sha256": report.get("private_receipt_sha256"),
        "public_rest_valid": report.get("public_rest_valid") is True,
        "public_websocket_valid": report.get("public_websocket_valid") is True,
        "private_account_rest_valid": report.get("private_account_rest_valid") is True,
        "private_account_websocket_valid": report.get("private_account_websocket_valid") is True,
        "block_reasons": list(report.get("block_reasons") or []),
        "credential_value_present": False,
        "raw_source_payload_included": False,
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "cancel_endpoint_called": False,
        "signature_created": False,
        "stark_private_key_accessed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "created_at_utc": report.get("created_at_utc"),
    }
    attestation["attestation_sha256"] = sha256_json(attestation)
    _assert_redacted(attestation)
    return attestation


def _build_registry_record(report: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "registry_version": P71_CLOSURE_REGISTRY_VERSION,
        "closure_report_id": report.get("closure_report_id"),
        "closure_report_sha256": report.get("closure_report_sha256"),
        "operator_session_id": report.get("operator_session_id"),
        "public_evidence_id": report.get("public_evidence_id"),
        "private_read_session_id": report.get("private_read_session_id"),
        "public_evidence_sha256": report.get("public_evidence_sha256"),
        "private_receipt_sha256": report.get("private_receipt_sha256"),
        "p71_complete": True,
        "credential_value_present": False,
        "network_write_call_performed": False,
        "testnet_order_submission_allowed": False,
        "consumed_at_utc": utc_now_canonical(),
    }
    record["registry_record_sha256"] = sha256_json(record)
    _assert_redacted(record)
    return record


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = list(report.get("block_reasons") or [])
    blocker_text = "\n".join(f"- `{item}`" for item in blockers) if blockers else "- None"
    return f"""# P71 Extended Testnet Read-only Closure Handoff

Status: `{report.get('status')}`

- P71 complete: `{str(bool(report.get('p71_complete'))).lower()}`
- Public REST valid: `{str(bool(report.get('public_rest_valid'))).lower()}`
- Public WebSocket valid: `{str(bool(report.get('public_websocket_valid'))).lower()}`
- Private REST valid: `{str(bool(report.get('private_account_rest_valid'))).lower()}`
- Private WebSocket valid: `{str(bool(report.get('private_account_websocket_valid'))).lower()}`
- Evidence consumed: `{str(bool(report.get('closure_evidence_consumed'))).lower()}`
- Ready for signed testnet execution: `false`
- Testnet order submission allowed: `false`

## Block reasons

{blocker_text}

## Safety boundary

This closure validates read-only connectivity evidence only. It does not enable signing, order submission, cancellation, executor activation, signed-testnet promotion, or live trading.
"""


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def persist_p71_closure_outputs(
    *,
    project_root: str | Path,
    public_evidence: Mapping[str, Any],
    private_receipt: Mapping[str, Any],
    operator_session_id: str | None = None,
    registry_path: str | Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    registry = Path(registry_path).resolve() if registry_path else root / "storage" / "registries" / "p71_consumed_evidence_registry.jsonl"
    closure_dir = root / "storage" / "p71" / "closure"
    latest_dir = root / "storage" / "latest"

    with _registry_lock(registry):
        records = load_registry_records(registry)
        report = build_p71_closure_report(
            public_evidence=public_evidence,
            private_receipt=private_receipt,
            consumed_registry_records=records,
            operator_session_id=operator_session_id,
            now_epoch_ms=now_epoch_ms,
        )
        if report["p71_complete"]:
            report = dict(report)
            report["closure_evidence_consumed"] = True
            report["closure_report_sha256"] = sha256_json({key: value for key, value in report.items() if key != "closure_report_sha256"})
        attestation = build_p71_redacted_attestation(report)
        attempt_dir = closure_dir / "attempts"
        _atomic_write_json(attempt_dir / f"{report['closure_report_id']}.json", report)
        _atomic_write_json(attempt_dir / f"{report['closure_report_id']}.attestation.json", attestation)
        _atomic_write_json(latest_dir / "p71_extended_readonly_closure_attempt_report.json", report)

        canonical_report_path = latest_dir / "p71_extended_readonly_closure_report.json"
        existing_canonical = _read_json_object(canonical_report_path)
        preserve_existing_complete = existing_canonical.get("p71_complete") is True and report.get("p71_complete") is not True
        if not preserve_existing_complete:
            _atomic_write_json(closure_dir / "p71_extended_readonly_closure_report.json", report)
            _atomic_write_json(closure_dir / "p71_extended_readonly_attestation.json", attestation)
            _atomic_write_json(canonical_report_path, report)
            _atomic_write_json(latest_dir / "p71_extended_readonly_attestation.json", attestation)
            _atomic_write_text(latest_dir / "P71_EXTENDED_READONLY_CLOSURE_HANDOFF.md", _build_handoff_markdown(report))
        else:
            _atomic_write_text(latest_dir / "P71_EXTENDED_READONLY_CLOSURE_ATTEMPT_HANDOFF.md", _build_handoff_markdown(report))

        if report["p71_complete"]:
            registry_record = _build_registry_record(report)
            _append_jsonl(registry, registry_record)
            _atomic_write_json(latest_dir / "p71_consumed_evidence_registry_record.json", registry_record)
        return report


__all__ = [
    "P71_CLOSURE_VERSION",
    "P71_CLOSURE_ATTESTATION_VERSION",
    "P71_CLOSURE_REGISTRY_VERSION",
    "P71_MAX_SOURCE_SKEW_SECONDS",
    "P71ClosureError",
    "load_registry_records",
    "build_p71_closure_report",
    "build_p71_redacted_attestation",
    "persist_p71_closure_outputs",
]
