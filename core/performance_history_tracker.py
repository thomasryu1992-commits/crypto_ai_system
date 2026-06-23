from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {
            "status": "INVALID_JSON_TYPE",
            "error": "JSON root is not an object.",
            "path": str(path),
        }

    except Exception as exc:
        return {
            "status": "LOAD_FAILED",
            "error": str(exc),
            "path": str(path),
        }


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_jsonl(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False))
        f.write("\n")


def first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return default


def latest_daily_report_file(storage_path: Path) -> Optional[Path]:
    reports_path = storage_path / "reports"

    candidates: List[Path] = []

    candidates.extend(storage_path.glob("daily_report_*.json"))
    candidates.extend(reports_path.glob("daily_report_*.json"))

    candidates = [
        path
        for path in candidates
        if path.is_file()
        and "scheduler" not in path.name.lower()
        and "health" not in path.name.lower()
        and "result" not in path.name.lower()
    ]

    if not candidates:
        return None

    candidates = sorted(
        candidates,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return candidates[0]


def safe_status(data: Dict[str, Any], default: str = "UNKNOWN") -> str:
    return str(
        first_non_empty(
            data.get("status"),
            data.get("overall_status"),
            data.get("result"),
            default=default,
        )
    )


def normalize_signal_side(value: Any) -> str:
    if value is None:
        return "UNKNOWN"

    text = str(value).strip().upper()

    if not text:
        return "UNKNOWN"

    return text


def extract_performance_record(storage_path: Path) -> Dict[str, Any]:
    daily_report_path = latest_daily_report_file(storage_path)

    daily_report = load_json_file(daily_report_path)
    paper_report = load_json_file(storage_path / "paper_performance_report.json")
    trading_cycle = load_json_file(storage_path / "trading_cycle_result.json")
    scheduler_health = load_json_file(storage_path / "scheduler_health_result.json")
    telegram_send = load_json_file(storage_path / "telegram_daily_report_send_result.json")
    markdown_report = load_json_file(storage_path / "daily_markdown_report_result.json")

    signal = paper_report.get("signal", {})
    if not isinstance(signal, dict):
        signal = {}

    report_date = first_non_empty(
        daily_report.get("report_date"),
        datetime.now(timezone.utc).date().isoformat(),
    )

    current_price = first_non_empty(
        daily_report.get("current_price"),
        paper_report.get("current_price"),
        trading_cycle.get("current_price"),
        scheduler_health.get("current_price"),
        default=None,
    )

    market_bias = first_non_empty(
        daily_report.get("market_bias"),
        paper_report.get("market_bias"),
        trading_cycle.get("market_bias"),
        default="UNKNOWN",
    )

    research_score = first_non_empty(
        daily_report.get("research_score"),
        paper_report.get("research_score"),
        trading_cycle.get("research_score"),
        default=None,
    )

    signal_side = normalize_signal_side(
        first_non_empty(
            signal.get("side"),
            trading_cycle.get("signal", {}).get("side") if isinstance(trading_cycle.get("signal"), dict) else None,
            default="UNKNOWN",
        )
    )

    signal_confidence = first_non_empty(
        signal.get("confidence"),
        trading_cycle.get("signal", {}).get("confidence") if isinstance(trading_cycle.get("signal"), dict) else None,
        default=None,
    )

    record = {
        "name": "PERFORMANCE_HISTORY_RECORD",
        "recorded_at_utc": now_utc(),
        "report_date": report_date,
        "current_price": current_price,
        "market_bias": market_bias,
        "research_score": research_score,
        "decision_type": first_non_empty(
            paper_report.get("decision_type"),
            trading_cycle.get("decision_type"),
            default="UNKNOWN",
        ),
        "signal_side": signal_side,
        "signal_confidence": signal_confidence,
        "signal_reason": first_non_empty(
            signal.get("reason"),
            paper_report.get("reason"),
            default="-",
        ),
        "position_opened": paper_report.get("position_opened", False),
        "trading_mode": first_non_empty(
            paper_report.get("mode"),
            trading_cycle.get("mode"),
            default="paper",
        ),
        "paper_status": safe_status(paper_report),
        "trading_cycle_status": safe_status(trading_cycle),
        "scheduler_status": safe_status(scheduler_health),
        "operational_dry_run": scheduler_health.get("operational_dry_run", "UNKNOWN"),
        "markdown_report": first_non_empty(
            scheduler_health.get("markdown_report"),
            markdown_report.get("status"),
            default="UNKNOWN",
        ),
        "telegram_daily_send": first_non_empty(
            scheduler_health.get("telegram_daily_send"),
            telegram_send.get("status"),
            default="UNKNOWN",
        ),
        "source_files": {
            "daily_report": str(daily_report_path) if daily_report_path else None,
            "paper_performance_report": str(storage_path / "paper_performance_report.json"),
            "trading_cycle_result": str(storage_path / "trading_cycle_result.json"),
            "scheduler_health_result": str(storage_path / "scheduler_health_result.json"),
            "telegram_daily_report_send_result": str(storage_path / "telegram_daily_report_send_result.json"),
            "daily_markdown_report_result": str(storage_path / "daily_markdown_report_result.json"),
        },
    }

    return record


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            data = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
        except Exception:
            continue

    return rows


def build_summary(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_records = len(history)

    if total_records == 0:
        return {
            "name": "PERFORMANCE_HISTORY_SUMMARY",
            "status": "NO_HISTORY",
            "total_records": 0,
            "timestamp_utc": now_utc(),
        }

    signal_counts: Dict[str, int] = {}
    bias_counts: Dict[str, int] = {}
    position_opened_count = 0

    scores: List[float] = []
    confidences: List[float] = []

    for row in history:
        signal_side = str(row.get("signal_side", "UNKNOWN")).upper()
        market_bias = str(row.get("market_bias", "UNKNOWN")).lower()

        signal_counts[signal_side] = signal_counts.get(signal_side, 0) + 1
        bias_counts[market_bias] = bias_counts.get(market_bias, 0) + 1

        if row.get("position_opened") is True:
            position_opened_count += 1

        try:
            if row.get("research_score") is not None:
                scores.append(float(row.get("research_score")))
        except Exception:
            pass

        try:
            if row.get("signal_confidence") is not None:
                confidences.append(float(row.get("signal_confidence")))
        except Exception:
            pass

    avg_score = sum(scores) / len(scores) if scores else None
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    latest = history[-1]

    return {
        "name": "PERFORMANCE_HISTORY_SUMMARY",
        "status": "SUMMARY_UPDATED",
        "total_records": total_records,
        "latest_report_date": latest.get("report_date"),
        "latest_price": latest.get("current_price"),
        "latest_market_bias": latest.get("market_bias"),
        "latest_signal_side": latest.get("signal_side"),
        "latest_scheduler_status": latest.get("scheduler_status"),
        "position_opened_count": position_opened_count,
        "signal_counts": signal_counts,
        "market_bias_counts": bias_counts,
        "average_research_score": avg_score,
        "average_signal_confidence": avg_confidence,
        "timestamp_utc": now_utc(),
    }


def update_performance_history(
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    history_path = storage_path / "performance_history.jsonl"
    summary_path = storage_path / "performance_history_summary.json"
    result_path = storage_path / "performance_history_update_result.json"

    record = extract_performance_record(storage_path)

    append_jsonl(history_path, record)

    history = load_history(history_path)
    summary = build_summary(history)

    write_json_file(summary_path, summary)

    result = {
        "name": "PERFORMANCE_HISTORY_TRACKER",
        "status": "HISTORY_UPDATED",
        "history_path": str(history_path),
        "summary_path": str(summary_path),
        "result_path": str(result_path),
        "latest_record": record,
        "summary": summary,
        "timestamp_utc": now_utc(),
    }

    write_json_file(result_path, result)

    return result


def main() -> None:
    result = update_performance_history(storage_dir="storage")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()