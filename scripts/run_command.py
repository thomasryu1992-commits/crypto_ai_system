from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AGENT_ID = "crypto_ai_system"
BLOCKED_COMMANDS = {
    "live",
    "live_trade",
    "execute_order",
    "place_order",
    "open_position",
    "close_position",
    "withdraw",
    "transfer",
}


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d_%H%M")


def _artifact_dir(root: Path, output_dir: str | None, defaults: dict) -> Path:
    raw = output_dir or defaults.get("artifact_base_dir") or "data/reports"
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _result(
    success: bool,
    status: str,
    command: str,
    summary: str | None = None,
    artifact_path: str | None = None,
    error_message: str | None = None,
    **extra: Any,
) -> dict:
    payload = {
        "success": success,
        "status": status,
        "agent_id": AGENT_ID,
        "command": command,
        "summary": summary,
        "artifact_path": artifact_path,
        "error_message": error_message,
    }
    payload.update(extra)
    return payload


def _print_result(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _relative_or_string(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_json_if_exists(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else default
    except Exception:
        return default


def _artifact_metadata_path(artifact: Path) -> Path:
    return artifact.with_name(f"{artifact.name}.metadata.json")


def _build_artifact_id(command: str, artifact_sha256: str, job_id: str | None) -> str:
    return hashlib.sha256(f"artifact|{AGENT_ID}|{command}|{artifact_sha256}|{job_id or ''}".encode("utf-8")).hexdigest()[:24]


def _record_artifact(
    root: Path,
    artifact_base: Path,
    artifact: Path,
    *,
    command: str,
    artifact_type: str,
    artifact_format: str,
    job_id: str | None,
    dry_run: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    artifact_sha256 = _file_sha256(artifact)
    metadata_path = _artifact_metadata_path(artifact)
    index_path = artifact_base / "artifact_index.json"
    latest_dir = artifact_base / "latest"
    latest_path = latest_dir / f"latest_{command}.json"
    artifact_id = _build_artifact_id(command, artifact_sha256, job_id)
    base_record: dict[str, Any] = {
        "artifact_registry_contract_version": "agent_artifact_registry_v1",
        "artifact_id": artifact_id,
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "command": command,
        "job_id": job_id or "",
        "dry_run": bool(dry_run),
        "artifact_type": artifact_type,
        "artifact_format": artifact_format,
        "artifact_path": _relative_or_string(root, artifact),
        "artifact_sha256": artifact_sha256,
        "artifact_metadata_path": _relative_or_string(root, metadata_path),
        "artifact_index_path": _relative_or_string(root, index_path),
        "latest_pointer_path": _relative_or_string(root, latest_path),
        "created_at_utc": created_at,
        "review_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "auto_position_open_enabled": False,
        "withdrawal_enabled": False,
        "fund_transfer_enabled": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    if extra:
        base_record.update(extra)

    sidecar_payload = dict(base_record)
    sidecar_payload["sidecar_contract_version"] = "agent_artifact_metadata_v1"
    sidecar_payload["stdout_json_links_to_sidecar"] = True
    _safe_json_write(metadata_path, sidecar_payload)
    metadata_sha256 = _file_sha256(metadata_path)

    record = dict(base_record)
    record["artifact_metadata_sha256"] = metadata_sha256
    record["artifact_registry_updated"] = True

    index_payload = _load_json_if_exists(
        index_path,
        {
            "artifact_index_contract_version": "agent_artifact_index_v1",
            "agent_id": AGENT_ID,
            "artifacts": [],
        },
    )
    artifacts = index_payload.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    artifacts = [item for item in artifacts if isinstance(item, dict) and item.get("artifact_id") != artifact_id]
    artifacts.append(record)
    index_payload.update(
        {
            "artifact_index_contract_version": "agent_artifact_index_v1",
            "agent_id": AGENT_ID,
            "agent_package_version": "0.286.0-agent.14",
            "updated_at_utc": created_at,
            "artifact_count": len(artifacts),
            "artifacts": artifacts[-500:],
            "review_only": True,
            "execution_permission_granted": False,
            "stage_transition_allowed": False,
        }
    )
    _safe_json_write(index_path, index_payload)

    latest_payload = dict(record)
    latest_payload["latest_pointer_contract_version"] = "agent_artifact_latest_pointer_v1"
    latest_payload["updated_at_utc"] = created_at
    _safe_json_write(latest_path, latest_payload)

    return record


def _assert_safe_defaults(defaults: dict) -> None:
    required_false = [
        "live_trading_enabled",
        "order_execution_enabled",
        "auto_position_open_enabled",
        "withdrawal_enabled",
        "fund_transfer_enabled",
    ]
    enabled = [key for key in required_false if defaults.get(key) is not False]
    if enabled:
        raise RuntimeError(f"Unsafe Local Launcher defaults: {', '.join(enabled)} must be false.")


def _front_matter_lines(metadata: dict[str, Any]) -> list[str]:
    lines = ["---"]
    for key in sorted(metadata):
        value = metadata[key]
        if isinstance(value, bool):
            rendered = str(value).lower()
        elif value is None:
            rendered = ""
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return lines


def _base_report_metadata(command: str, symbol: str | None, job_id: str | None, dry_run: bool) -> dict[str, Any]:
    created = _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "artifact_contract_version": "agent_report_v2",
        "command": command,
        "created_at": created,
        "job_id": job_id or "",
        "mode": "local_launcher",
        "dry_run": bool(dry_run),
        "review_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "auto_position_open_enabled": False,
        "withdrawal_enabled": False,
        "fund_transfer_enabled": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    if symbol:
        metadata["symbol"] = symbol
    return metadata


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""]


def _safety_footer() -> list[str]:
    return _section(
        "Safety & Permission State",
        [
            "- live_trading_enabled: false",
            "- order_execution_enabled: false",
            "- auto_position_open_enabled: false",
            "- withdrawal_enabled: false",
            "- fund_transfer_enabled: false",
            "- execution_permission_granted: false",
            "- stage_transition_allowed: false",
            "- order_endpoint_called: false",
            "- secret_value_accessed: false",
            "",
            "This artifact is generated for Thomas Agent OS Local Launcher review-only operation. It must not be interpreted as permission to submit signed testnet or live orders.",
        ],
    )


def _write_report_artifact(
    path: Path,
    *,
    command: str,
    symbol: str | None,
    job_id: str | None,
    dry_run: bool,
    title: str,
    sections: list[tuple[str, list[str]]],
) -> None:
    metadata = _base_report_metadata(command, symbol, job_id, dry_run)
    content: list[str] = [*_front_matter_lines(metadata), "", f"# {title}", ""]
    for section_title, section_lines in sections:
        content.extend(_section(section_title, section_lines))
    content.extend(_safety_footer())
    content.extend(
        _section(
            "Artifact Contract",
            [
                "- artifact_format: markdown",
                "- artifact_contract_version: agent_report_v2",
                "- stdout_contract: final line JSON",
                "- storage_target: data/reports",
                "- launcher_scope: package-owned command output only",
            ],
        )
    )
    path.write_text("\n".join(content), encoding="utf-8")

def _run_daily(root: Path, artifact_base: Path, defaults: dict[str, Any], job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    today = now.strftime("%Y-%m-%d")
    source_payload = _build_source_health_payload(root, defaults, job_id, dry_run, now)
    source_fields = _source_health_stdout_fields(source_payload)
    artifact = artifact_base / f"crypto_daily_{today}.md"
    _write_report_artifact(
        artifact,
        command="daily",
        symbol=None,
        job_id=job_id,
        dry_run=dry_run,
        title="Daily Crypto Report",
        sections=[
            (
                "Executive Summary",
                [
                    "- Overall posture: neutral / review-only",
                    "- Covered symbols: BTC, ETH",
                    "- Operating mode: Thomas Agent OS Local Launcher",
                    "- Live trading and real order execution remain disabled.",
                ],
            ),
            (
                "Market Coverage",
                [
                    "| Symbol | Bias | Risk Level | Permission |",
                    "|---|---|---|---|",
                    "| BTC | Neutral | Medium | review_only |",
                    "| ETH | Neutral | Medium | review_only |",
                    "",
                    "Local Launcher dry-run mode does not fetch fresh paid data by default. Missing optional data is treated as neutral for reporting only and must not become signed-testnet or live execution evidence.",
                ],
            ),
            (
                "Source & Feature Lineage",
                [
                    f"- source_health_id: {source_payload.get('source_health_id')}",
                    f"- data_snapshot_id: {source_payload.get('data_snapshot_id')}",
                    f"- feature_snapshot_id: {source_payload.get('feature_snapshot_id')}",
                    f"- feature_snapshot_created: {str(bool(source_payload.get('feature_snapshot_created'))).lower()}",
                    f"- feature_matrix_sha256: {source_payload.get('feature_matrix_sha256')}",
                    "- Feature lineage is review-only evidence and does not grant trading permission.",
                ],
            ),
            (
                "ResearchSignal Status",
                [
                    "- ResearchSignal output is available through the `signal` command.",
                    "- Daily report keeps signal posture descriptive unless a validated ResearchSignal artifact is supplied by the internal pipeline.",
                    "- Legacy, stale, fallback, sample, or synthetic signal evidence must not unlock execution.",
                ],
            ),
            (
                "Risk Guard Status",
                [
                    "- PreOrderRiskGate hot-path execution is not invoked by this command.",
                    "- No order intent is created.",
                    "- No signed request is created.",
                    "- No exchange order/status/cancel endpoint is called.",
                ],
            ),
            (
                "Operator Next Actions",
                [
                    "- Use `/run crypto scan BTC` for a symbol-level market scan.",
                    "- Use `/run crypto signal BTC` for a ResearchSignal JSON artifact.",
                    "- Treat this report as review-only market context, not as execution authorization.",
                ],
            ),
        ],
    )
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="daily",
        artifact_type="report",
        artifact_format="markdown",
        job_id=job_id,
        dry_run=dry_run,
    )
    return _result(
        True,
        "completed",
        "daily",
        "Daily crypto report generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="report",
        artifact_format="markdown",
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        **source_fields,
        review_only=True,
        execution_permission_granted=False,
        stage_transition_allowed=False,
    )


def _run_scan(root: Path, artifact_base: Path, defaults: dict[str, Any], symbol: str, job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    source_payload = _build_source_health_payload(root, defaults, job_id, dry_run, now)
    source_fields = _source_health_stdout_fields(source_payload)
    normalized = symbol.upper()
    artifact = artifact_base / f"crypto_scan_{normalized}_{_safe_datetime(now)}.md"
    _write_report_artifact(
        artifact,
        command="scan",
        symbol=normalized,
        job_id=job_id,
        dry_run=dry_run,
        title=f"{normalized} Market Scan",
        sections=[
            (
                "Executive Summary",
                [
                    f"- Symbol: {normalized}",
                    "- Bias: Neutral",
                    "- Risk level: Medium",
                    "- Permission: review_only",
                    "- Live trading and real order execution remain disabled.",
                ],
            ),
            (
                "Market Structure Review",
                [
                    "- Trend state: not asserted without fresh validated market data",
                    "- Support/resistance: not asserted without fresh validated market data",
                    "- Volatility posture: neutral_due_to_missing_optional_data",
                    "- Optional derivatives/on-chain/flow data: explicit neutral placeholder in Local Launcher dry-run mode",
                ],
            ),
            (
                "Source & Feature Lineage",
                [
                    f"- source_health_id: {source_payload.get('source_health_id')}",
                    f"- data_snapshot_id: {source_payload.get('data_snapshot_id')}",
                    f"- feature_snapshot_id: {source_payload.get('feature_snapshot_id')}",
                    f"- feature_snapshot_created: {str(bool(source_payload.get('feature_snapshot_created'))).lower()}",
                    f"- feature_matrix_sha256: {source_payload.get('feature_matrix_sha256')}",
                    "- Sample/stale/invalid CSV inputs block feature snapshot creation and cannot become candidates.",
                ],
            ),
            (
                "ResearchSignal Compatibility",
                [
                    "- This scan artifact is not a ResearchSignal decision object.",
                    "- Use the `signal` command to create a ResearchSignal JSON artifact.",
                    "- Trading logic must consume ResearchSignal and PreOrderRiskGate outputs separately.",
                ],
            ),
            (
                "Execution Guard",
                [
                    "- No order intent is created.",
                    "- No paper/testnet/live order endpoint is called.",
                    "- No secret value is read.",
                    "- No runtime setting is mutated.",
                ],
            ),
            (
                "Operator Next Actions",
                [
                    f"- For deeper analysis, run `/run crypto signal {normalized}`.",
                    "- For strategy validation, use backtest/paper review-only commands with explicit approval where required.",
                    "- Do not treat scan output as execution approval.",
                ],
            ),
        ],
    )
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="scan",
        artifact_type="report",
        artifact_format="markdown",
        job_id=job_id,
        dry_run=dry_run,
        extra={"symbol": normalized},
    )
    return _result(
        True,
        "completed",
        "scan",
        f"{normalized} market scan generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="report",
        artifact_format="markdown",
        symbol=normalized,
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        **source_fields,
        review_only=True,
        execution_permission_granted=False,
        stage_transition_allowed=False,
    )

def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


PRICE_CSV_REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
SAMPLE_PRICE_MARKERS = {"sample", "fixture", "mock", "synthetic", "fallback", "example"}


def _resolve_local_price_data_dir(root: Path, defaults: dict[str, Any]) -> Path:
    raw = str(defaults.get("local_price_data_dir") or "data/price_data")
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path


def _looks_sample_like(path: Path, rows: list[dict[str, str]]) -> bool:
    path_text = "/".join(part.lower() for part in path.parts)
    if any(marker in path_text for marker in SAMPLE_PRICE_MARKERS):
        return True
    for row in rows:
        for key in ("sample_flag", "fixture_flag", "mock_flag", "synthetic_flag", "fallback_flag"):
            value = str(row.get(key, "")).strip().lower()
            if value in {"1", "true", "yes", "y"}:
                return True
    return False


def _parse_price_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.isdigit():
            number = int(raw)
            if number > 10_000_000_000:
                number = number // 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _validate_numeric_price_rows(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows[:50], start=1):
        parsed_values: dict[str, float] = {}
        for col in ["open", "high", "low", "close", "volume"]:
            try:
                parsed_values[col] = float(str(row.get(col, "")).strip())
            except Exception:
                errors.append(f"row_{idx}_{col}_not_numeric")
                continue
        if {"open", "high", "low", "close"}.issubset(parsed_values):
            if parsed_values["high"] < max(parsed_values["open"], parsed_values["close"], parsed_values["low"]):
                errors.append(f"row_{idx}_high_below_ohlc")
            if parsed_values["low"] > min(parsed_values["open"], parsed_values["close"], parsed_values["high"]):
                errors.append(f"row_{idx}_low_above_ohlc")
        if parsed_values.get("volume", 0.0) < 0:
            errors.append(f"row_{idx}_volume_negative")
    return errors


def _validate_local_price_csv(root: Path, defaults: dict[str, Any], now: datetime) -> dict[str, Any]:
    data_dir = _resolve_local_price_data_dir(root, defaults)
    max_age_hours = int(defaults.get("local_price_data_max_age_hours") or 48)
    result: dict[str, Any] = {
        "source_name": "price",
        "source_type": "local_price_csv",
        "required": True,
        "local_price_data_dir": _relative_or_string(root, data_dir),
        "local_csv_detected": False,
        "price_csv_schema_valid": False,
        "price_csv_row_count": 0,
        "price_csv_required_columns": sorted(PRICE_CSV_REQUIRED_COLUMNS),
        "price_csv_missing_columns": sorted(PRICE_CSV_REQUIRED_COLUMNS),
        "price_data_connected": False,
        "fresh_price_data_available": False,
        "sample_flag": False,
        "sample_used": False,
        "fallback_flag": False,
        "fallback_used": False,
        "synthetic_flag": False,
        "synthetic_used": False,
        "mock_flag": False,
        "mock_used": False,
        "stale": False,
        "missing": True,
        "fresh": False,
        "freshness_sec": None,
        "status": "missing_local_price_csv",
        "status_reason": "LOCAL_PRICE_DATA_DIR_MISSING_OR_EMPTY",
        "selected_price_csv": None,
        "selected_price_csv_sha256": None,
        "latest_price_timestamp_utc": None,
        "data_snapshot_id": None,
        "data_snapshot_manifest_sha256": None,
        "schema_errors": [],
        "trading_candidate_allowed": False,
        "paper_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
    }
    if not data_dir.exists() or not data_dir.is_dir():
        result["source_hash"] = _sha256_json(result)
        return result
    csv_files = sorted([p for p in data_dir.glob("*.csv") if p.is_file()])
    result["price_csv_file_count"] = len(csv_files)
    if not csv_files:
        result["source_hash"] = _sha256_json(result)
        return result
    selected = csv_files[0]
    result["local_csv_detected"] = True
    result["selected_price_csv"] = _relative_or_string(root, selected)
    result["selected_price_csv_sha256"] = _file_sha256(selected)
    try:
        with selected.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = {str(name or "").strip() for name in (reader.fieldnames or [])}
            missing_columns = sorted(PRICE_CSV_REQUIRED_COLUMNS - fieldnames)
            result["price_csv_missing_columns"] = missing_columns
            rows = list(reader)
    except Exception as exc:
        result["status"] = "invalid_local_price_csv_read_error"
        result["status_reason"] = f"PRICE_CSV_READ_ERROR:{exc.__class__.__name__}"
        result["schema_errors"] = [result["status_reason"]]
        result["source_hash"] = _sha256_json(result)
        return result
    result["price_csv_row_count"] = len(rows)
    numeric_errors = _validate_numeric_price_rows(rows)
    timestamp_values = [_parse_price_timestamp(row.get("timestamp", "")) for row in rows]
    timestamp_values = [item for item in timestamp_values if item is not None]
    schema_errors = []
    if result["price_csv_missing_columns"]:
        schema_errors.append("PRICE_CSV_REQUIRED_COLUMNS_MISSING")
    if not rows:
        schema_errors.append("PRICE_CSV_NO_ROWS")
    if not timestamp_values:
        schema_errors.append("PRICE_CSV_NO_PARSEABLE_TIMESTAMP")
    schema_errors.extend(numeric_errors[:20])
    result["schema_errors"] = schema_errors
    result["price_csv_schema_valid"] = not schema_errors
    sample_like = _looks_sample_like(selected, rows)
    result["sample_flag"] = sample_like
    result["sample_used"] = sample_like
    if not result["price_csv_schema_valid"]:
        result["missing"] = False
        result["status"] = "invalid_local_price_csv_schema"
        result["status_reason"] = "PRICE_CSV_SCHEMA_VALIDATION_FAILED"
        result["source_hash"] = _sha256_json(result)
        return result
    latest_ts = max(timestamp_values)
    result["latest_price_timestamp_utc"] = latest_ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    freshness = max(0, int((now - latest_ts).total_seconds()))
    result["freshness_sec"] = freshness
    fresh = freshness <= max_age_hours * 3600
    result["fresh"] = fresh
    result["fresh_price_data_available"] = fresh and not sample_like
    result["stale"] = not fresh
    result["missing"] = False
    snapshot_basis = {
        "selected_price_csv_sha256": result["selected_price_csv_sha256"],
        "latest_price_timestamp_utc": result["latest_price_timestamp_utc"],
        "row_count": result["price_csv_row_count"],
        "sample_flag": sample_like,
    }
    result["data_snapshot_id"] = _stable_id("data_snapshot", _sha256_json(snapshot_basis))
    result["data_snapshot_manifest_sha256"] = _sha256_json(snapshot_basis)
    if sample_like:
        result["status"] = "sample_price_csv_detected_review_only"
        result["status_reason"] = "SAMPLE_PRICE_CSV_BLOCKS_CANDIDATE_ELIGIBILITY"
    elif not fresh:
        result["status"] = "stale_local_price_csv"
        result["status_reason"] = "LOCAL_PRICE_CSV_TIMESTAMP_STALE"
    else:
        result["status"] = "local_price_csv_connected_fresh_review_only"
        result["status_reason"] = "LOCAL_PRICE_CSV_SCHEMA_AND_FRESHNESS_VALID_REVIEW_ONLY"
        result["price_data_connected"] = True
    result["source_hash"] = _sha256_json(result)
    return result


def _resolve_selected_price_csv(root: Path, selected_price_csv: str | None) -> Path | None:
    if not selected_price_csv:
        return None
    path = Path(selected_price_csv)
    if not path.is_absolute():
        path = root / path
    return path if path.exists() and path.is_file() else None


def _read_price_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_price_feature_snapshot(root: Path, defaults: dict[str, Any], price_record: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Build a minimal review-only price feature snapshot from a validated local CSV.

    Feature creation is intentionally blocked for missing, invalid, stale, sample,
    fixture, mock, synthetic, or fallback sources. A blocked result may still be
    referenced by reports/signals for lineage diagnostics, but it is not a usable
    feature snapshot for signed-testnet/live candidacy.
    """
    base: dict[str, Any] = {
        "feature_snapshot_contract_version": "price_feature_snapshot_v1",
        "feature_snapshot_created": False,
        "feature_snapshot_status": "blocked_review_only",
        "feature_snapshot_status_reason": "PRICE_FEATURE_SNAPSHOT_REQUIRES_FRESH_REAL_LOCAL_PRICE_CSV",
        "feature_snapshot_id": None,
        "feature_snapshot_manifest_sha256": None,
        "feature_matrix_sha256": None,
        "feature_source_data_snapshot_id": price_record.get("data_snapshot_id"),
        "feature_snapshot_row_count": 0,
        "feature_snapshot_feature_columns": list(defaults.get("price_feature_columns") or [
            "latest_close",
            "previous_close",
            "close_return_1",
            "high_low_range_pct",
            "latest_volume",
            "row_count",
        ]),
        "feature_snapshot_blocked_by_sample_stale_invalid": True,
        "review_only": True,
        "trading_candidate_allowed": False,
        "paper_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
    }
    blockers: list[str] = []
    if not price_record.get("price_data_connected"):
        blockers.append(str(price_record.get("status_reason") or price_record.get("status") or "PRICE_DATA_NOT_CONNECTED"))
    if price_record.get("sample_flag") or price_record.get("sample_used"):
        blockers.append("SAMPLE_PRICE_CSV_BLOCKS_FEATURE_SNAPSHOT")
    if price_record.get("stale"):
        blockers.append("STALE_PRICE_CSV_BLOCKS_FEATURE_SNAPSHOT")
    if not price_record.get("price_csv_schema_valid"):
        blockers.append("INVALID_PRICE_CSV_SCHEMA_BLOCKS_FEATURE_SNAPSHOT")
    if price_record.get("fallback_flag") or price_record.get("synthetic_flag") or price_record.get("mock_flag"):
        blockers.append("FALLBACK_SYNTHETIC_MOCK_SOURCE_BLOCKS_FEATURE_SNAPSHOT")
    selected_path = _resolve_selected_price_csv(root, price_record.get("selected_price_csv"))
    if selected_path is None:
        blockers.append("SELECTED_PRICE_CSV_NOT_FOUND")
    if blockers:
        base["feature_snapshot_status_reason"] = ";".join(dict.fromkeys(blockers))
        base["feature_matrix_sha256"] = _sha256_json({
            "feature_snapshot_created": False,
            "feature_source_data_snapshot_id": base.get("feature_source_data_snapshot_id"),
            "blockers": blockers,
            "price_status": price_record.get("status"),
        })
        base["feature_snapshot_id"] = _stable_id("feature_snapshot_blocked", str(base.get("feature_source_data_snapshot_id") or "missing"), base["feature_matrix_sha256"])
        base["feature_snapshot_manifest_sha256"] = _sha256_json({
            "feature_snapshot_id": base["feature_snapshot_id"],
            "feature_matrix_sha256": base["feature_matrix_sha256"],
            "feature_snapshot_created": False,
            "blockers": blockers,
        })
        return base

    try:
        rows = _read_price_csv_rows(selected_path)
    except Exception as exc:
        base["feature_snapshot_status_reason"] = f"PRICE_CSV_READ_ERROR_FOR_FEATURES:{exc.__class__.__name__}"
        base["feature_matrix_sha256"] = _sha256_json(base)
        base["feature_snapshot_id"] = _stable_id("feature_snapshot_blocked", str(base.get("feature_source_data_snapshot_id") or "missing"), base["feature_matrix_sha256"])
        base["feature_snapshot_manifest_sha256"] = _sha256_json({"feature_snapshot_id": base["feature_snapshot_id"], "feature_matrix_sha256": base["feature_matrix_sha256"]})
        return base

    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_price_timestamp(row.get("timestamp", ""))
        if ts is None:
            continue
        try:
            parsed_rows.append({
                "timestamp": ts,
                "symbol": str(row.get("symbol", "")).upper(),
                "open": float(row.get("open", "")),
                "high": float(row.get("high", "")),
                "low": float(row.get("low", "")),
                "close": float(row.get("close", "")),
                "volume": float(row.get("volume", "")),
            })
        except Exception:
            continue
    if not parsed_rows:
        base["feature_snapshot_status_reason"] = "NO_PARSEABLE_ROWS_FOR_FEATURE_SNAPSHOT"
        base["feature_matrix_sha256"] = _sha256_json(base)
        base["feature_snapshot_id"] = _stable_id("feature_snapshot_blocked", str(base.get("feature_source_data_snapshot_id") or "missing"), base["feature_matrix_sha256"])
        base["feature_snapshot_manifest_sha256"] = _sha256_json({"feature_snapshot_id": base["feature_snapshot_id"], "feature_matrix_sha256": base["feature_matrix_sha256"]})
        return base

    parsed_rows.sort(key=lambda item: item["timestamp"])
    latest = parsed_rows[-1]
    previous = parsed_rows[-2] if len(parsed_rows) >= 2 else latest
    previous_close = previous["close"]
    close_return_1 = ((latest["close"] / previous_close) - 1.0) if previous_close else 0.0
    high_low_range_pct = ((latest["high"] - latest["low"]) / latest["close"]) if latest["close"] else 0.0
    symbols = sorted({row["symbol"] for row in parsed_rows if row.get("symbol")})
    feature_matrix = {
        "feature_matrix_contract_version": "price_feature_matrix_v1",
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "source": "local_price_csv",
        "source_csv_sha256": price_record.get("selected_price_csv_sha256"),
        "data_snapshot_id": price_record.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": price_record.get("data_snapshot_manifest_sha256"),
        "row_count": len(parsed_rows),
        "symbols": symbols,
        "latest_timestamp_utc": latest["timestamp"].replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "features": {
            "latest_symbol": latest.get("symbol"),
            "latest_close": latest["close"],
            "previous_close": previous_close,
            "close_return_1": close_return_1,
            "high_low_range_pct": high_low_range_pct,
            "latest_volume": latest["volume"],
            "row_count": len(parsed_rows),
        },
        "review_only": True,
        "trading_candidate_allowed": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
    }
    feature_matrix_sha256 = _sha256_json(feature_matrix)
    feature_snapshot_id = _stable_id("feature_snapshot", str(price_record.get("data_snapshot_id") or "missing"), feature_matrix_sha256)
    manifest_sha256 = _sha256_json({
        "feature_snapshot_id": feature_snapshot_id,
        "feature_matrix_sha256": feature_matrix_sha256,
        "data_snapshot_id": price_record.get("data_snapshot_id"),
        "source_csv_sha256": price_record.get("selected_price_csv_sha256"),
        "feature_snapshot_contract_version": "price_feature_snapshot_v1",
    })
    base.update({
        "feature_snapshot_created": True,
        "feature_snapshot_status": "created_review_only",
        "feature_snapshot_status_reason": "FRESH_REAL_LOCAL_PRICE_CSV_FEATURE_SNAPSHOT_CREATED_REVIEW_ONLY",
        "feature_snapshot_id": feature_snapshot_id,
        "feature_snapshot_manifest_sha256": manifest_sha256,
        "feature_matrix_sha256": feature_matrix_sha256,
        "feature_source_data_snapshot_id": price_record.get("data_snapshot_id"),
        "feature_snapshot_row_count": len(parsed_rows),
        "feature_snapshot_feature_columns": list(feature_matrix["features"].keys()),
        "feature_snapshot_blocked_by_sample_stale_invalid": False,
        "feature_matrix": feature_matrix,
    })
    return base


def _source_health_stdout_fields(source_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_health_contract_version": "source_health_review_v1",
        "source_health_id": source_payload.get("source_health_id"),
        "source_bundle_sha256": source_payload.get("source_bundle_sha256"),
        "source_health_status": source_payload.get("price_source_status"),
        "price_data_hard_required": True,
        "price_data_connected": bool(source_payload.get("price_data_connected")),
        "fresh_price_data_available": bool(source_payload.get("fresh_price_data_available")),
        "local_csv_detected": bool(source_payload.get("local_csv_detected")),
        "price_csv_schema_valid": bool(source_payload.get("price_csv_schema_valid")),
        "selected_price_csv": source_payload.get("selected_price_csv"),
        "selected_price_csv_sha256": source_payload.get("selected_price_csv_sha256"),
        "data_snapshot_id": source_payload.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": source_payload.get("data_snapshot_manifest_sha256"),
        "feature_snapshot_contract_version": "price_feature_snapshot_v1",
        "feature_snapshot_created": bool(source_payload.get("feature_snapshot_created")),
        "feature_snapshot_status": source_payload.get("feature_snapshot_status"),
        "feature_snapshot_status_reason": source_payload.get("feature_snapshot_status_reason"),
        "feature_snapshot_id": source_payload.get("feature_snapshot_id"),
        "feature_snapshot_manifest_sha256": source_payload.get("feature_snapshot_manifest_sha256"),
        "feature_matrix_sha256": source_payload.get("feature_matrix_sha256"),
        "feature_source_data_snapshot_id": source_payload.get("feature_source_data_snapshot_id"),
        "feature_snapshot_row_count": source_payload.get("feature_snapshot_row_count"),
        "optional_data_policy": "neutral_due_to_missing",
        "trading_candidate_allowed": False,
        "paper_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
    }


def _optional_data_health_for_local_launcher(price_record: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    price = price_record or {
        "source_name": "price",
        "required": True,
        "status": "missing_local_price_csv",
        "fresh": False,
        "stale": False,
        "missing": True,
        "neutral_due_to_missing": False,
        "source_hash": _sha256_json({"source_name": "price", "status": "missing_local_price_csv", "required": True}),
        "freshness_sec": None,
        "trading_candidate_allowed": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
    }
    return {
        "price": price,
        "binance_futures_public": {
            "required": False,
            "status": "neutral_due_to_missing",
            "neutral_due_to_missing": True,
            "trading_candidate_allowed": False,
        },
        "coin_metrics_community": {
            "required": False,
            "status": "neutral_due_to_missing",
            "neutral_due_to_missing": True,
            "trading_candidate_allowed": False,
        },
        "farside_btc_etf_flow": {
            "required": False,
            "status": "neutral_due_to_missing",
            "neutral_due_to_missing": True,
            "trading_candidate_allowed": False,
        },
        "defillama_stablecoin": {
            "required": False,
            "status": "neutral_due_to_missing",
            "neutral_due_to_missing": True,
            "trading_candidate_allowed": False,
        },
    }

def _build_research_signal_v2_payload(root: Path, defaults: dict[str, Any], symbol: str, job_id: str | None, dry_run: bool, now: datetime) -> dict[str, Any]:
    normalized = symbol.upper()
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timeframe = "1h"
    profile_id = "profile_local_launcher_review_only_v1"
    config_version = "agent_package_defaults_v0.286.0-agent.14"
    source_health = _build_source_health_payload(root, defaults, job_id, dry_run, now)
    price_record = source_health.get("optional_data_health", {}).get("price", {})
    optional_health = _optional_data_health_for_local_launcher(price_record)
    data_snapshot_id = source_health.get("data_snapshot_id") or hashlib.sha256(f"data|{normalized}|{timeframe}|{created_at}|local_launcher_price_csv_missing".encode()).hexdigest()[:24]
    feature_snapshot = source_health.get("feature_snapshot") if isinstance(source_health.get("feature_snapshot"), dict) else {}
    feature_snapshot_created = bool(source_health.get("feature_snapshot_created"))
    feature_snapshot_id = source_health.get("feature_snapshot_id") or _stable_id("feature_snapshot_blocked", data_snapshot_id, str(source_health.get("source_health_id") or "missing"))
    feature_matrix = feature_snapshot.get("feature_matrix") if isinstance(feature_snapshot.get("feature_matrix"), dict) else {
        "feature_matrix_contract_version": "price_feature_matrix_v1_blocked",
        "symbol": normalized,
        "timeframe": timeframe,
        "created_at_utc": created_at,
        "source_mode": "local_launcher_price_csv_dry_run",
        "price_data_connected": bool(source_health.get("price_data_connected")),
        "fresh_price_data_available": bool(source_health.get("fresh_price_data_available")),
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_created": False,
        "feature_snapshot_status": source_health.get("feature_snapshot_status"),
        "source_health_id": source_health.get("source_health_id"),
        "optional_data_health": optional_health,
        "review_only": True,
        "trading_candidate_allowed": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
    }
    feature_matrix_sha256 = source_health.get("feature_matrix_sha256") or _sha256_json(feature_matrix)
    source_bundle = {
        "agent_id": AGENT_ID,
        "symbol": normalized,
        "timeframe": timeframe,
        "source_mode": "local_launcher_price_csv_dry_run",
        "source_health_id": source_health.get("source_health_id"),
        "price_source_status": source_health.get("price_source_status"),
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_id": feature_snapshot_id,
        "feature_snapshot_created": feature_snapshot_created,
        "feature_matrix_sha256": feature_matrix_sha256,
        "selected_price_csv_sha256": source_health.get("selected_price_csv_sha256"),
        "optional_sources": sorted(optional_health),
    }
    source_bundle_sha256 = _sha256_json(source_bundle)
    research_signal_id = hashlib.sha256(
        f"signal|{normalized}|{timeframe}|{created_at}|{profile_id}|{feature_snapshot_id}|{feature_matrix_sha256}".encode()
    ).hexdigest()[:24]
    missing_optional_count = sum(
        1
        for name, status in optional_health.items()
        if name != "price" and status.get("status") == "neutral_due_to_missing"
    )
    price_connected = bool(source_health.get("price_data_connected"))
    fresh_price = bool(source_health.get("fresh_price_data_available"))
    payload: dict[str, Any] = {
        "schema_version": "2.0",
        "artifact_contract_version": "research_signal_v2_agent_package_contract",
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "command": "signal",
        "job_id": job_id,
        "symbol": normalized,
        "timeframe": timeframe,
        "created_at_utc": created_at,
        "generated_at": created_at,
        "research_signal_id": research_signal_id,
        "signal_id": research_signal_id,
        "signal_version": "research_signal_v2_agent_package_contract_v1",
        "profile_id": profile_id,
        "profile_version": "local_launcher_review_only_profile_v1",
        "config_version": config_version,
        "source_health_id": source_health.get("source_health_id"),
        "source_health_status": source_health.get("price_source_status"),
        "source_health_contract_version": "source_health_review_v1",
        "data_snapshot_id": data_snapshot_id,
        "data_snapshot_manifest_sha256": source_health.get("data_snapshot_manifest_sha256") or _sha256_json({"data_snapshot_id": data_snapshot_id, "source_bundle_sha256": source_bundle_sha256}),
        "feature_snapshot_contract_version": "price_feature_snapshot_v1",
        "feature_snapshot_created": feature_snapshot_created,
        "feature_snapshot_status": source_health.get("feature_snapshot_status"),
        "feature_snapshot_status_reason": source_health.get("feature_snapshot_status_reason"),
        "feature_snapshot_id": feature_snapshot_id,
        "feature_snapshot_manifest_sha256": source_health.get("feature_snapshot_manifest_sha256"),
        "feature_source_data_snapshot_id": source_health.get("feature_source_data_snapshot_id"),
        "feature_snapshot_row_count": source_health.get("feature_snapshot_row_count"),
        "feature_matrix_sha256": feature_matrix_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "optional_data_health": optional_health,
        "missing_optional_source_count": missing_optional_count,
        "stale_optional_source_count": source_health.get("stale_optional_source_count", 0),
        "neutral_due_to_missing": True,
        "missing_optional_data_neutral": True,
        "live_eligibility": False,
        "live_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "paper_candidate_eligible": False,
        "review_only": True,
        "local_launcher_dry_run": bool(dry_run),
        "generated_from_fresh_market_data": fresh_price,
        "data_source": "local_price_csv" if price_connected else "local_launcher_wrapper",
        "data_source_role": "review_only_local_csv" if price_connected else "review_only_placeholder",
        "data_quality_status": source_health.get("price_source_status"),
        "data_freshness_sec": price_record.get("freshness_sec"),
        "trading_allowed_by_data_source": False,
        "market_condition": "range",
        "market_regime": "REVIEW_ONLY_PRICE_FEATURES_AVAILABLE" if feature_snapshot_created else "UNKNOWN_WITHOUT_VALID_FEATURE_SNAPSHOT",
        "bias": "neutral",
        "score_bias": "NEUTRAL",
        "long_score": 50,
        "short_score": 50,
        "score_total": 0.0,
        "confidence": 0.5,
        "risk_level": "blocked_review_only",
        "entry_side": "FLAT",
        "entry_allowed": False,
        "entry_confidence": 0.0,
        "block_reasons": [
            str(source_health.get("price_source_status_reason") or source_health.get("price_source_status")),
            str(source_health.get("feature_snapshot_status_reason") or source_health.get("feature_snapshot_status")),
            "MISSING_OPTIONAL_DATA_NEUTRAL_FOR_REPORTING_ONLY",
            "LIVE_AND_SIGNED_TESTNET_ELIGIBILITY_FALSE",
        ],
        "risk_warnings": [
            "This ResearchSignal artifact is schema-compatible review-only output, not execution authorization.",
            "Feature snapshot lineage is recorded for auditability only and does not grant trading permission.",
        ],
        "score_components": {
            "price_direction": None,
            "derivatives_positioning": None,
            "exchange_flow": None,
            "etf_flow": None,
            "stablecoin_liquidity": None,
            "risk": None,
        },
        "features": feature_matrix,
        "trade_permission": {
            "result": "blocked_review_only",
            "allowed": False,
            "reduced": False,
            "blocked": True,
            "neutral_due_to_missing": True,
            "execution_permission_granted": False,
            "stage_transition_allowed": False,
        },
        "price_context": {
            "price_data_required": True,
            "price_data_connected": price_connected,
            "fresh_price_data_available": fresh_price,
            "local_csv_detected": bool(source_health.get("local_csv_detected")),
            "selected_price_csv_sha256": source_health.get("selected_price_csv_sha256"),
            "data_snapshot_id": data_snapshot_id,
            "feature_snapshot_id": feature_snapshot_id,
            "feature_snapshot_created": feature_snapshot_created,
            "feature_matrix_sha256": feature_matrix_sha256,
        },
        "scenarios": {
            "long": {"allowed": False, "reason": "execution remains disabled in Agent Package review-only mode"},
            "short": {"allowed": False, "reason": "execution remains disabled in Agent Package review-only mode"},
            "neutral": {"allowed": True, "reason": "review-only signal context"},
        },
        "fallback_flag": False,
        "fallback_used": False,
        "synthetic_flag": False,
        "synthetic_used": False,
        "sample_flag": bool(source_health.get("sample_flag")),
        "sample_used": bool(source_health.get("sample_used")),
        "legacy_fallback_used": False,
        "legacy_signal_used": False,
        "stale_optional_data": False,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "auto_position_open_enabled": False,
        "withdrawal_enabled": False,
        "fund_transfer_enabled": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    return payload

def _run_signal(root: Path, artifact_base: Path, defaults: dict[str, Any], symbol: str, job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    normalized = symbol.upper()
    artifact = artifact_base / f"research_signal_{normalized}_{_safe_datetime(now)}.json"
    payload = _build_research_signal_v2_payload(root, defaults, normalized, job_id, dry_run, now)
    artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="signal",
        artifact_type="signal",
        artifact_format="json",
        job_id=job_id,
        dry_run=dry_run,
        extra={
            "symbol": normalized,
            "research_signal_id": payload["research_signal_id"],
            "signal_version": payload["signal_version"],
            "data_snapshot_id": payload.get("data_snapshot_id"),
            "feature_snapshot_id": payload.get("feature_snapshot_id"),
            "feature_snapshot_created": payload.get("feature_snapshot_created"),
            "feature_matrix_sha256": payload.get("feature_matrix_sha256"),
            "live_eligibility": False,
            "live_candidate_eligible": False,
        },
    )
    return _result(
        True,
        "completed",
        "signal",
        f"{normalized} ResearchSignal v2 artifact generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="signal",
        artifact_format="json",
        symbol=normalized,
        research_signal_id=payload["research_signal_id"],
        signal_version=payload["signal_version"],
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        source_health_contract_version="source_health_review_v1",
        source_health_id=payload.get("source_health_id"),
        source_bundle_sha256=payload.get("source_bundle_sha256"),
        source_health_status=payload.get("source_health_status"),
        price_data_hard_required=True,
        price_data_connected=payload.get("price_context", {}).get("price_data_connected", False),
        fresh_price_data_available=payload.get("price_context", {}).get("fresh_price_data_available", False),
        local_csv_detected=payload.get("price_context", {}).get("local_csv_detected", False),
        selected_price_csv_sha256=payload.get("price_context", {}).get("selected_price_csv_sha256"),
        data_snapshot_id=payload.get("data_snapshot_id"),
        data_snapshot_manifest_sha256=payload.get("data_snapshot_manifest_sha256"),
        feature_snapshot_contract_version="price_feature_snapshot_v1",
        feature_snapshot_created=payload.get("feature_snapshot_created"),
        feature_snapshot_status=payload.get("feature_snapshot_status"),
        feature_snapshot_id=payload.get("feature_snapshot_id"),
        feature_snapshot_manifest_sha256=payload.get("feature_snapshot_manifest_sha256"),
        feature_matrix_sha256=payload.get("feature_matrix_sha256"),
        feature_source_data_snapshot_id=payload.get("feature_source_data_snapshot_id"),
        optional_data_policy="neutral_due_to_missing",
        missing_optional_source_count=payload["missing_optional_source_count"],
        stale_optional_source_count=payload["stale_optional_source_count"],
        trading_candidate_allowed=False,
        review_only=True,
        live_eligibility=False,
        live_candidate_eligible=False,
        execution_permission_granted=False,
        stage_transition_allowed=False,
    )


def _stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    joined = "|".join(str(part) for part in parts)
    return hashlib.sha256(f"{prefix}|{joined}".encode("utf-8")).hexdigest()[:length]


def _build_review_source_bundle(command: str, created_at: str, job_id: str | None, dry_run: bool) -> dict[str, Any]:
    return {
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "command": command,
        "created_at_utc": created_at,
        "job_id": job_id or "",
        "dry_run": bool(dry_run),
        "source_mode": "local_launcher_review_only",
        "fresh_market_data_required": False,
        "real_order_execution_allowed": False,
        "runtime_settings_mutation_allowed": False,
    }


def _write_backtest_artifact(root: Path, artifact_base: Path, job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    backtest_id = _stable_id("backtest", created_at, job_id or "", str(bool(dry_run)))
    source_bundle = _build_review_source_bundle("backtest", created_at, job_id, dry_run)
    source_artifact_sha256 = _sha256_json(source_bundle)
    artifact = artifact_base / f"crypto_backtest_{_safe_datetime(now)}.md"
    _write_report_artifact(
        artifact,
        command="backtest",
        symbol=None,
        job_id=job_id,
        dry_run=dry_run,
        title="Crypto Backtest Review",
        sections=[
            (
                "Backtest Contract",
                [
                    f"- backtest_id: {backtest_id}",
                    "- backtest_contract_version: backtest_review_v1",
                    f"- source_artifact_sha256: {source_artifact_sha256}",
                    "- artifact_type: backtest",
                    "- mode: review_only",
                    "- historical_data_only: true",
                    "- live_execution_allowed: false",
                ],
            ),
            (
                "Execution Scope",
                [
                    "- This command may summarize historical strategy review output only.",
                    "- It does not create an order intent.",
                    "- It does not invoke paper/testnet/live execution adapters.",
                    "- It does not mutate runtime settings, leverage, margin, or risk limits.",
                ],
            ),
            (
                "Review Metrics Placeholder",
                [
                    "| Metric | Value | Status |",
                    "|---|---:|---|",
                    "| trades_evaluated | 0 | local_launcher_dry_run |",
                    "| expectancy_r | 0.0 | not_computed_without_dataset |",
                    "| max_drawdown_r | 0.0 | not_computed_without_dataset |",
                    "| win_rate | 0.0 | not_computed_without_dataset |",
                    "",
                    "No live, signed testnet, or paper execution evidence is generated by this Agent Package wrapper command.",
                ],
            ),
            (
                "Operator Next Actions",
                [
                    "- Attach validated historical datasets through the internal backtesting pipeline before treating metrics as research evidence.",
                    "- Keep ResearchSignal, strategy decision, and PreOrderRiskGate evidence separate.",
                    "- Do not promote this wrapper artifact to signed testnet/live candidacy.",
                ],
            ),
        ],
    )
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="backtest",
        artifact_type="backtest",
        artifact_format="markdown",
        job_id=job_id,
        dry_run=dry_run,
        extra={
            "backtest_id": backtest_id,
            "backtest_contract_version": "backtest_review_v1",
            "source_artifact_sha256": source_artifact_sha256,
            "historical_data_only": True,
            "live_candidate_eligible": False,
            "signed_testnet_candidate_eligible": False,
        },
    )
    return _result(
        True,
        "completed",
        "backtest",
        "Backtest review artifact generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="backtest",
        artifact_format="markdown",
        backtest_id=backtest_id,
        backtest_contract_version="backtest_review_v1",
        source_artifact_sha256=source_artifact_sha256,
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        review_only=True,
        historical_data_only=True,
        execution_permission_granted=False,
        stage_transition_allowed=False,
        live_candidate_eligible=False,
        signed_testnet_candidate_eligible=False,
    )


def _write_feedback_artifact(root: Path, artifact_base: Path, job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    feedback_cycle_id = _stable_id("feedback", created_at, job_id or "", str(bool(dry_run)))
    outcome_review_id = _stable_id("outcome_review", feedback_cycle_id, created_at)
    source_bundle = _build_review_source_bundle("feedback", created_at, job_id, dry_run)
    source_artifact_sha256 = _sha256_json(source_bundle)
    artifact = artifact_base / f"crypto_feedback_{_safe_datetime(now)}.md"
    _write_report_artifact(
        artifact,
        command="feedback",
        symbol=None,
        job_id=job_id,
        dry_run=dry_run,
        title="Crypto Feedback Review",
        sections=[
            (
                "Feedback Contract",
                [
                    f"- feedback_cycle_id: {feedback_cycle_id}",
                    f"- outcome_review_id: {outcome_review_id}",
                    "- feedback_contract_version: feedback_review_v1",
                    f"- source_artifact_sha256: {source_artifact_sha256}",
                    "- artifact_type: feedback",
                    "- mode: review_only",
                    "- runtime_mutation_allowed: false",
                ],
            ),
            (
                "Outcome Analytics Scope",
                [
                    "- expectancy: not_computed_without_outcome_dataset",
                    "- win_loss: not_computed_without_outcome_dataset",
                    "- average_r: not_computed_without_outcome_dataset",
                    "- drawdown: not_computed_without_outcome_dataset",
                    "- slippage: not_computed_without_execution_evidence",
                    "- latency: not_computed_without_execution_evidence",
                    "- rejection_rate: not_computed_without_submission_history",
                    "- paper_testnet_live_gap: not_computed_without_testnet_live_evidence",
                ],
            ),
            (
                "Feedback Permissions",
                [
                    "- Feedback may create reports, review notes, and future candidate drafts only.",
                    "- Feedback must not directly change score weights or runtime settings.",
                    "- Feedback must not grant signed testnet/live execution permission.",
                    "- Any runtime-impacting change still requires the full manual approval chain.",
                ],
            ),
            (
                "Operator Next Actions",
                [
                    "- Provide outcome_id and reconciliation_id evidence before using this as strategy feedback.",
                    "- Compare paper/testnet/live gaps only after real signed testnet/live evidence exists.",
                    "- Treat this artifact as review-only feedback context.",
                ],
            ),
        ],
    )
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="feedback",
        artifact_type="feedback",
        artifact_format="markdown",
        job_id=job_id,
        dry_run=dry_run,
        extra={
            "feedback_cycle_id": feedback_cycle_id,
            "outcome_review_id": outcome_review_id,
            "feedback_contract_version": "feedback_review_v1",
            "source_artifact_sha256": source_artifact_sha256,
            "runtime_mutation_allowed": False,
            "live_candidate_eligible": False,
            "signed_testnet_candidate_eligible": False,
        },
    )
    return _result(
        True,
        "completed",
        "feedback",
        "Feedback review artifact generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="feedback",
        artifact_format="markdown",
        feedback_cycle_id=feedback_cycle_id,
        outcome_review_id=outcome_review_id,
        feedback_contract_version="feedback_review_v1",
        source_artifact_sha256=source_artifact_sha256,
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        review_only=True,
        runtime_mutation_allowed=False,
        execution_permission_granted=False,
        stage_transition_allowed=False,
        live_candidate_eligible=False,
        signed_testnet_candidate_eligible=False,
    )



def _build_source_health_payload(root: Path, defaults: dict[str, Any], job_id: str | None, dry_run: bool, now: datetime) -> dict[str, Any]:
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    price_csv_status = _validate_local_price_csv(root, defaults, now)
    sources = _optional_data_health_for_local_launcher(price_csv_status)
    source_records: dict[str, dict[str, Any]] = {}
    missing_optional_count = 0
    stale_optional_count = 0
    for name, item in sources.items():
        required = bool(item.get("required"))
        status = str(item.get("status"))
        if name == "price":
            source_records[name] = dict(item)
        else:
            source_records[name] = {
                "source_name": name,
                "required": required,
                "status": status,
                "fresh": False,
                "stale": False,
                "missing": status in {"neutral_due_to_missing", "not_connected_in_local_launcher_dry_run", "missing"},
                "neutral_due_to_missing": bool(item.get("neutral_due_to_missing")),
                "source_hash": _sha256_json({"source_name": name, "status": status, "required": required}),
                "freshness_sec": None,
                "trading_candidate_allowed": False,
                "signed_testnet_candidate_eligible": False,
                "live_candidate_eligible": False,
            }
        if not required and status == "neutral_due_to_missing":
            missing_optional_count += 1
        if not required and status == "stale":
            stale_optional_count += 1
    source_bundle_sha256 = _sha256_json(source_records)
    source_health_id = _stable_id("source_health", created_at, job_id or "", source_bundle_sha256)
    price_record = source_records.get("price", {})
    feature_snapshot = _build_price_feature_snapshot(root, defaults, price_record, now)
    price_connected = bool(price_record.get("price_data_connected"))
    fresh_price = bool(price_record.get("fresh_price_data_available"))
    sample_flag = bool(price_record.get("sample_flag"))
    stale_required = bool(price_record.get("stale"))
    if price_connected:
        gate_reason = "LOCAL_PRICE_CSV_CONNECTED_FRESH_BUT_REVIEW_ONLY"
        gate_result = "review_only_valid_price_data"
    else:
        gate_reason = str(price_record.get("status_reason") or "PRICE_DATA_NOT_CONNECTED")
        gate_result = "blocked_review_only"
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_contract_version": "source_health_review_v1",
        "agent_id": AGENT_ID,
        "agent_package_version": "0.286.0-agent.14",
        "command": "source-health",
        "job_id": job_id or "",
        "created_at_utc": created_at,
        "source_health_id": source_health_id,
        "source_bundle_sha256": source_bundle_sha256,
        "price_data_hard_required": True,
        "price_source_status": price_record.get("status", "unknown"),
        "price_source_status_reason": price_record.get("status_reason", "unknown"),
        "price_data_connected": price_connected,
        "fresh_price_data_available": fresh_price,
        "local_price_data_dir": price_record.get("local_price_data_dir"),
        "local_csv_detected": bool(price_record.get("local_csv_detected")),
        "price_csv_schema_valid": bool(price_record.get("price_csv_schema_valid")),
        "price_csv_row_count": int(price_record.get("price_csv_row_count") or 0),
        "price_csv_missing_columns": price_record.get("price_csv_missing_columns") or [],
        "selected_price_csv": price_record.get("selected_price_csv"),
        "selected_price_csv_sha256": price_record.get("selected_price_csv_sha256"),
        "latest_price_timestamp_utc": price_record.get("latest_price_timestamp_utc"),
        "data_snapshot_id": price_record.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": price_record.get("data_snapshot_manifest_sha256"),
        "feature_snapshot_contract_version": "price_feature_snapshot_v1",
        "feature_snapshot_created": bool(feature_snapshot.get("feature_snapshot_created")),
        "feature_snapshot_status": feature_snapshot.get("feature_snapshot_status"),
        "feature_snapshot_status_reason": feature_snapshot.get("feature_snapshot_status_reason"),
        "feature_snapshot_id": feature_snapshot.get("feature_snapshot_id"),
        "feature_snapshot_manifest_sha256": feature_snapshot.get("feature_snapshot_manifest_sha256"),
        "feature_matrix_sha256": feature_snapshot.get("feature_matrix_sha256"),
        "feature_source_data_snapshot_id": feature_snapshot.get("feature_source_data_snapshot_id"),
        "feature_snapshot_row_count": feature_snapshot.get("feature_snapshot_row_count"),
        "feature_snapshot_feature_columns": feature_snapshot.get("feature_snapshot_feature_columns"),
        "feature_snapshot_blocked_by_sample_stale_invalid": feature_snapshot.get("feature_snapshot_blocked_by_sample_stale_invalid"),
        "feature_snapshot": feature_snapshot,
        "required_source_missing_count": 0 if not price_record.get("missing") else 1,
        "missing_optional_source_count": missing_optional_count,
        "stale_optional_source_count": stale_optional_count,
        "optional_data_policy": "neutral_due_to_missing",
        "optional_data_health": source_records,
        "source_status_summary": {
            "price": price_record.get("status", "unknown"),
            "price_status_reason": price_record.get("status_reason", "unknown"),
            "local_csv_detected": bool(price_record.get("local_csv_detected")),
            "price_csv_schema_valid": bool(price_record.get("price_csv_schema_valid")),
            "fresh_required_sources_ready": fresh_price,
            "optional_missing_neutral": missing_optional_count,
            "optional_stale": stale_optional_count,
        },
        "fallback_flag": bool(price_record.get("fallback_flag")),
        "fallback_used": bool(price_record.get("fallback_used")),
        "synthetic_flag": bool(price_record.get("synthetic_flag")),
        "synthetic_used": bool(price_record.get("synthetic_used")),
        "sample_flag": sample_flag,
        "sample_used": bool(price_record.get("sample_used")),
        "mock_flag": bool(price_record.get("mock_flag")),
        "mock_used": bool(price_record.get("mock_used")),
        "stale_required_data": stale_required,
        "hidden_missing_source_detected": False,
        "source_gate": {
            "result": gate_result,
            "reason": gate_reason,
            "price_required": True,
            "price_data_connected": price_connected,
            "fresh_price_data_available": fresh_price,
            "optional_missing_is_neutral_for_reporting_only": True,
            "fallback_sample_synthetic_source_blocks_candidates": True,
            "feature_snapshot_created": bool(feature_snapshot.get("feature_snapshot_created")),
            "feature_snapshot_status": feature_snapshot.get("feature_snapshot_status"),
            "feature_snapshot_blocks_sample_stale_invalid_csv": True,
            "trading_candidate_allowed": False,
            "signed_testnet_candidate_eligible": False,
            "live_candidate_eligible": False,
        },
        "review_only": True,
        "local_launcher_dry_run": bool(dry_run),
        "trading_candidate_allowed": False,
        "paper_candidate_eligible": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "auto_position_open_enabled": False,
        "withdrawal_enabled": False,
        "fund_transfer_enabled": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "exchange_adapter_called": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_settings_mutated": False,
        "block_reasons": [
            gate_reason,
            "OPTIONAL_DATA_MISSING_MARKED_NEUTRAL_DUE_TO_MISSING",
            "SOURCE_HEALTH_ARTIFACT_IS_REVIEW_ONLY_NOT_EXECUTION_EVIDENCE",
        ],
    }
    return payload

def _run_source_health(root: Path, artifact_base: Path, defaults: dict[str, Any], job_id: str | None, dry_run: bool) -> dict:
    now = _utc_now()
    artifact = artifact_base / f"source_health_{_safe_datetime(now)}.json"
    payload = _build_source_health_payload(root, defaults, job_id, dry_run, now)
    artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    stdout_fields = _source_health_stdout_fields(payload)
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="source-health",
        artifact_type="source_health",
        artifact_format="json",
        job_id=job_id,
        dry_run=dry_run,
        extra={
            **stdout_fields,
            "source_health_id": payload["source_health_id"],
            "source_bundle_sha256": payload["source_bundle_sha256"],
            "missing_optional_source_count": payload["missing_optional_source_count"],
            "stale_optional_source_count": payload["stale_optional_source_count"],
        },
    )
    return _result(
        True,
        "completed",
        "source-health",
        "Source health review artifact generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="source_health",
        artifact_format="json",
        source_health_id=payload["source_health_id"],
        source_health_contract_version="source_health_review_v1",
        source_bundle_sha256=payload["source_bundle_sha256"],
        price_data_hard_required=True,
        price_data_connected=payload["price_data_connected"],
        fresh_price_data_available=payload["fresh_price_data_available"],
        local_csv_detected=payload["local_csv_detected"],
        price_csv_schema_valid=payload["price_csv_schema_valid"],
        selected_price_csv=payload["selected_price_csv"],
        selected_price_csv_sha256=payload["selected_price_csv_sha256"],
        data_snapshot_id=payload["data_snapshot_id"],
        data_snapshot_manifest_sha256=payload["data_snapshot_manifest_sha256"],
        feature_snapshot_contract_version="price_feature_snapshot_v1",
        feature_snapshot_created=payload.get("feature_snapshot_created"),
        feature_snapshot_status=payload.get("feature_snapshot_status"),
        feature_snapshot_status_reason=payload.get("feature_snapshot_status_reason"),
        feature_snapshot_id=payload.get("feature_snapshot_id"),
        feature_snapshot_manifest_sha256=payload.get("feature_snapshot_manifest_sha256"),
        feature_matrix_sha256=payload.get("feature_matrix_sha256"),
        feature_source_data_snapshot_id=payload.get("feature_source_data_snapshot_id"),
        feature_snapshot_row_count=payload.get("feature_snapshot_row_count"),
        missing_optional_source_count=payload["missing_optional_source_count"],
        stale_optional_source_count=payload["stale_optional_source_count"],
        optional_data_policy="neutral_due_to_missing",
        trading_candidate_allowed=False,
        paper_candidate_eligible=False,
        signed_testnet_candidate_eligible=False,
        live_candidate_eligible=False,
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        review_only=True,
        execution_permission_granted=False,
        stage_transition_allowed=False,
    )

def _build_paper_simulation_contract(job_id: str | None, dry_run: bool, approved: bool, now: datetime) -> dict[str, Any]:
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    approval_source = "dry_run_bypass_for_review_only" if dry_run else "operator_approved_flag"
    paper_session_id = _stable_id("paper_session", created_at, job_id or "", str(bool(dry_run)), approval_source)
    paper_run_id = _stable_id("paper_run", paper_session_id, created_at)
    simulation_scope_id = _stable_id("paper_scope", "local_launcher_review_only", job_id or "", created_at)
    source_bundle = _build_review_source_bundle("paper", created_at, job_id, dry_run)
    source_bundle.update(
        {
            "paper_simulation_contract_version": "paper_simulation_review_v1",
            "approval_required": True,
            "approval_source": approval_source,
            "paper_session_id": paper_session_id,
            "paper_run_id": paper_run_id,
            "simulation_scope_id": simulation_scope_id,
        }
    )
    source_artifact_sha256 = _sha256_json(source_bundle)
    return {
        "paper_simulation_contract_version": "paper_simulation_review_v1",
        "paper_session_id": paper_session_id,
        "paper_run_id": paper_run_id,
        "simulation_scope_id": simulation_scope_id,
        "source_artifact_sha256": source_artifact_sha256,
        "approval_required": True,
        "approval_satisfied_for_local_launcher_command": bool(dry_run or approved),
        "approval_source": approval_source,
        "approval_grants_real_execution": False,
        "simulation_mode": "local_launcher_review_only",
        "historical_or_paper_only": True,
        "paper_trading_enabled": True,
        "paper_simulation_allowed": True,
        "paper_order_submission_performed": False,
        "paper_execution_adapter_called": False,
        "order_intent_created": False,
        "execution_id": "not_created_in_agent_package_wrapper",
        "reconciliation_id": "not_created_in_agent_package_wrapper",
        "outcome_id": "not_created_in_agent_package_wrapper",
        "feedback_cycle_id": "not_created_in_agent_package_wrapper",
        "real_order_execution_allowed": False,
        "signed_testnet_candidate_eligible": False,
        "live_candidate_eligible": False,
        "execution_permission_granted": False,
        "stage_transition_allowed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "exchange_adapter_called": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "review_metrics": {
            "paper_orders_created": 0,
            "paper_fills_created": 0,
            "paper_positions_opened": 0,
            "pnl_r": 0.0,
            "max_drawdown_r": 0.0,
            "slippage_bps": None,
            "latency_ms": None,
            "status": "not_computed_without_validated_paper_dataset",
        },
        "operator_next_gate": "validated_paper_dataset_and_review_only_outcome_evidence_required",
    }


def _run_paper_report(root: Path, artifact_base: Path, job_id: str | None, dry_run: bool, approved: bool) -> dict:
    now = _utc_now()
    created_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    contract = _build_paper_simulation_contract(job_id, dry_run, approved, now)
    artifact = artifact_base / f"crypto_paper_{_safe_datetime(now)}.md"
    _write_report_artifact(
        artifact,
        command="paper",
        symbol=None,
        job_id=job_id,
        dry_run=dry_run,
        title="Crypto Paper Trading Simulation Review",
        sections=[
            (
                "Paper Simulation Contract",
                [
                    f"- paper_session_id: {contract['paper_session_id']}",
                    f"- paper_run_id: {contract['paper_run_id']}",
                    f"- simulation_scope_id: {contract['simulation_scope_id']}",
                    "- paper_simulation_contract_version: paper_simulation_review_v1",
                    f"- source_artifact_sha256: {contract['source_artifact_sha256']}",
                    "- artifact_type: paper_simulation",
                    "- mode: local_launcher_review_only",
                    "- historical_or_paper_only: true",
                    "- approval_required: true",
                    f"- approval_source: {contract['approval_source']}",
                    "- approval_grants_real_execution: false",
                ],
            ),
            (
                "Execution Boundary",
                [
                    "- This command creates a paper simulation review artifact only.",
                    "- It does not create a real order intent.",
                    "- It does not call paper/testnet/live exchange adapters from this Agent Package wrapper.",
                    "- It does not submit, poll, cancel, or reconcile exchange orders.",
                    "- It does not read secret values or create signed requests.",
                    "- It does not mutate runtime settings, score weights, leverage, margin, or risk limits.",
                ],
            ),
            (
                "Paper Review Metrics Placeholder",
                [
                    "| Metric | Value | Status |",
                    "|---|---:|---|",
                    "| paper_orders_created | 0 | wrapper_review_only |",
                    "| paper_fills_created | 0 | wrapper_review_only |",
                    "| paper_positions_opened | 0 | wrapper_review_only |",
                    "| pnl_r | 0.0 | not_computed_without_validated_paper_dataset |",
                    "| max_drawdown_r | 0.0 | not_computed_without_validated_paper_dataset |",
                    "| slippage_bps | n/a | not_computed_without_execution_evidence |",
                    "| latency_ms | n/a | not_computed_without_execution_evidence |",
                    "",
                    "A future internal paper pipeline may generate paper execution evidence, but this Agent Package wrapper does not create execution evidence by itself.",
                ],
            ),
            (
                "Candidate Eligibility",
                [
                    "- paper_candidate_eligible: false",
                    "- signed_testnet_candidate_eligible: false",
                    "- live_candidate_eligible: false",
                    "- validated_paper_dataset_required: true",
                    "- outcome_evidence_required: true",
                    "- manual_approval_chain_required_for_runtime_impact: true",
                ],
            ),
            (
                "Operator Next Actions",
                [
                    "- Use this artifact as a review-only paper simulation placeholder.",
                    "- Connect validated paper datasets before computing paper performance.",
                    "- Keep paper results, ResearchSignal, TradeDecision, and PreOrderRiskGate evidence separate.",
                    "- Do not treat this artifact as signed testnet or live readiness evidence.",
                ],
            ),
        ],
    )
    record = _record_artifact(
        root,
        artifact_base,
        artifact,
        command="paper",
        artifact_type="paper_simulation",
        artifact_format="markdown",
        job_id=job_id,
        dry_run=dry_run,
        extra=contract,
    )
    return _result(
        True,
        "completed",
        "paper",
        "Paper simulation review artifact generated successfully.",
        _relative_or_string(root, artifact),
        artifact_type="paper_simulation",
        artifact_format="markdown",
        paper_simulation_contract_version="paper_simulation_review_v1",
        paper_session_id=contract["paper_session_id"],
        paper_run_id=contract["paper_run_id"],
        simulation_scope_id=contract["simulation_scope_id"],
        source_artifact_sha256=contract["source_artifact_sha256"],
        approval_required=True,
        approval_satisfied_for_local_launcher_command=contract["approval_satisfied_for_local_launcher_command"],
        approval_source=contract["approval_source"],
        approval_grants_real_execution=False,
        paper_order_submission_performed=False,
        paper_execution_adapter_called=False,
        order_intent_created=False,
        artifact_id=record["artifact_id"],
        artifact_sha256=record["artifact_sha256"],
        artifact_metadata_path=record["artifact_metadata_path"],
        artifact_metadata_sha256=record["artifact_metadata_sha256"],
        artifact_index_path=record["artifact_index_path"],
        latest_pointer_path=record["latest_pointer_path"],
        artifact_registry_updated=True,
        review_only=True,
        execution_permission_granted=False,
        stage_transition_allowed=False,
        live_candidate_eligible=False,
        signed_testnet_candidate_eligible=False,
        order_endpoint_called=False,
        order_status_endpoint_called=False,
        cancel_endpoint_called=False,
        exchange_adapter_called=False,
        signed_request_created=False,
        secret_value_accessed=False,
        runtime_settings_mutated=False,
    )

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thomas Agent OS entrypoint for Crypto AI System.")
    parser.add_argument("--command", required=True)
    parser.add_argument("--symbol")
    parser.add_argument("--output-dir")
    parser.add_argument("--config")
    parser.add_argument("--job-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args(argv)

    root = _root_dir()
    command = args.command.strip().lower()

    try:
        defaults = _load_json(Path(args.config) if args.config else root / "config" / "defaults.json")
        command_map = _load_json(root / "config" / "command_map.json")
        _assert_safe_defaults(defaults)

        if command in BLOCKED_COMMANDS:
            _print_result(_result(False, "blocked", command, error_message="Live trading is disabled in Local Launcher mode."))
            return 5

        if command not in command_map:
            _print_result(_result(False, "failed", command, error_message=f"Unknown command: {command}"))
            return 4

        command_info = command_map[command]
        if command_info.get("enabled") is not True or command_info.get("safe_in_local_launcher") is not True:
            _print_result(_result(False, "blocked", command, error_message=f"Command is disabled in Local Launcher mode: {command}"))
            return 5

        if command_info.get("requires_symbol") and not args.symbol:
            _print_result(_result(False, "failed", command, error_message=f"Command requires --symbol: {command}"))
            return 4

        if command_info.get("requires_approval") and not (args.approved or args.dry_run):
            _print_result(_result(False, "blocked", command, error_message=f"Command requires approval in Local Launcher mode: {command}"))
            return 5

        artifact_base = _artifact_dir(root, args.output_dir, defaults)

        if command == "daily":
            payload = _run_daily(root, artifact_base, defaults, args.job_id, args.dry_run)
        elif command == "scan":
            payload = _run_scan(root, artifact_base, defaults, args.symbol or "BTC", args.job_id, args.dry_run)
        elif command == "signal":
            payload = _run_signal(root, artifact_base, defaults, args.symbol or "BTC", args.job_id, args.dry_run)
        elif command == "source-health":
            payload = _run_source_health(root, artifact_base, defaults, args.job_id, args.dry_run)
        elif command == "backtest":
            payload = _write_backtest_artifact(root, artifact_base, args.job_id, args.dry_run)
        elif command == "feedback":
            payload = _write_feedback_artifact(root, artifact_base, args.job_id, args.dry_run)
        elif command == "paper":
            payload = _run_paper_report(root, artifact_base, args.job_id, args.dry_run, args.approved)
        else:
            payload = _result(False, "failed", command, error_message=f"Command has no handler: {command}")
            _print_result(payload)
            return 4

        _print_result(payload)
        return 0
    except RuntimeError as exc:
        _print_result(_result(False, "blocked", command, error_message=str(exc)))
        return 5
    except OSError as exc:
        _print_result(_result(False, "failed", command, error_message=f"Artifact or file error: {exc}"))
        return 6
    except Exception as exc:
        _print_result(_result(False, "failed", command, error_message=str(exc)))
        return 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
