from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def load_json_file(path: Path) -> Dict[str, Any]:
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


def safe_get(data: Dict[str, Any], key: str, default: Any = "-") -> Any:
    value = data.get(key, default)
    if value is None:
        return default
    return value


def format_price(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "-"


def format_score(value: Any) -> str:
    try:
        return f"{int(value)}/100"
    except Exception:
        return "-"


def format_confidence(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "-"


def bool_to_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "-"
    return str(value)


def get_latest_daily_report_path(storage_path: Path, report_date: Optional[str] = None) -> Path:
    if report_date:
        candidate = storage_path / f"daily_report_{report_date}.json"
        if candidate.exists():
            return candidate

    today_utc = datetime.now(timezone.utc).date().isoformat()
    today_candidate = storage_path / f"daily_report_{today_utc}.json"
    if today_candidate.exists():
        return today_candidate

    candidates = sorted(
        storage_path.glob("daily_report_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if candidates:
        return candidates[0]

    return today_candidate


def build_daily_markdown_report(
    daily_report: Dict[str, Any],
    paper_report: Dict[str, Any],
    scheduler_health: Dict[str, Any],
) -> str:
    report_date = safe_get(
        daily_report,
        "report_date",
        datetime.now(timezone.utc).date().isoformat(),
    )

    current_price = safe_get(
        daily_report,
        "current_price",
        scheduler_health.get("current_price", "-"),
    )

    market_bias = safe_get(daily_report, "market_bias", "-")
    research_score = safe_get(daily_report, "research_score", "-")

    summary = daily_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    base_case = safe_get(summary, "base_case", "-")
    key_reason = safe_get(summary, "key_reason", "-")
    risk_note = safe_get(summary, "risk_note", "-")

    signal = paper_report.get("signal", {})
    if not isinstance(signal, dict):
        signal = {}

    signal_side = safe_get(signal, "side", "-")
    signal_confidence = safe_get(signal, "confidence", "-")
    signal_reason = safe_get(signal, "reason", "-")

    scheduler_status = safe_get(scheduler_health, "status", "-")
    operational_dry_run = safe_get(scheduler_health, "operational_dry_run", "-")
    trading_cycle = safe_get(scheduler_health, "trading_cycle", "-")
    trading_bot = safe_get(scheduler_health, "trading_bot", "-")
    spreadsheet = safe_get(scheduler_health, "spreadsheet", "-")
    telegram = safe_get(scheduler_health, "telegram", "-")
    total_checks = safe_get(scheduler_health, "total_checks", "-")

    error_failures = scheduler_health.get("error_failures", [])
    warning_failures = scheduler_health.get("warning_failures", [])

    error_count = len(error_failures) if isinstance(error_failures, list) else "-"
    warning_count = len(warning_failures) if isinstance(warning_failures, list) else "-"

    generated_utc = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Crypto AI System Daily Report",
        "",
        "## 1. Report Overview",
        "",
        "| Item | Value |",
        "|---|---:|",
        f"| Report Date | {report_date} |",
        f"| Generated UTC | {generated_utc} |",
        f"| Current Price | {format_price(current_price)} |",
        f"| Market Bias | {market_bias} |",
        f"| Research Score | {format_score(research_score)} |",
        "",
        "---",
        "",
        "## 2. Market Research Summary",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Base Case | {base_case} |",
        f"| Key Reason | {key_reason} |",
        f"| Risk Note | {risk_note} |",
        "",
        "### Interpretation",
        "",
        f"The system is currently classifying the market as **{market_bias}** with a research score of **{format_score(research_score)}**.",
        "",
        f"Base case: **{base_case}**",
        "",
        "This means the system is not forcing a directional trade unless confirmation conditions improve.",
        "",
        "---",
        "",
        "## 3. Paper Trading Status",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Mode | {safe_get(paper_report, 'mode', '-')} |",
        f"| Signal | {signal_side} |",
        f"| Confidence | {format_confidence(signal_confidence)} |",
        f"| Position Opened | {bool_to_text(safe_get(paper_report, 'position_opened', '-'))} |",
        f"| Reason | {safe_get(paper_report, 'reason', '-')} |",
        "",
        "### Signal Reason",
        "",
        str(signal_reason),
        "",
        "---",
        "",
        "## 4. Scheduler Health",
        "",
        "| Check | Status |",
        "|---|---|",
        f"| Scheduler Status | {scheduler_status} |",
        f"| Operational Dry Run | {operational_dry_run} |",
        f"| Trading Cycle | {trading_cycle} |",
        f"| Trading Bot | {trading_bot} |",
        f"| Spreadsheet Sync | {spreadsheet} |",
        f"| Telegram | {telegram} |",
        f"| Total Checks | {total_checks} |",
        f"| Error Failures | {error_count} |",
        f"| Warning Failures | {warning_count} |",
        "",
        "---",
        "",
        "## 5. Final Decision",
        "",
        "```text",
        f"Market Bias: {market_bias}",
        f"Research Score: {format_score(research_score)}",
        f"Trading Signal: {signal_side}",
        f"Execution Mode: {safe_get(paper_report, 'mode', '-')}",
        f"Position Opened: {bool_to_text(safe_get(paper_report, 'position_opened', '-'))}",
        "```",
        "",
        "### Conclusion",
        "",
        f"Current system decision: **{signal_side}**",
        "",
        "The system remains in paper/dry-run mode and does not execute live orders.",
        "",
    ]

    return "\n".join(lines)


def write_daily_markdown_report(
    storage_dir: str | Path = "storage",
    report_date: Optional[str] = None,
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    reports_path = storage_path / "reports"

    storage_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    daily_report_path = get_latest_daily_report_path(
        storage_path=storage_path,
        report_date=report_date,
    )

    daily_report = load_json_file(daily_report_path)
    paper_report = load_json_file(storage_path / "paper_performance_report.json")
    scheduler_health = load_json_file(storage_path / "scheduler_health_result.json")

    final_report_date = report_date or daily_report.get("report_date")
    if not final_report_date:
        final_report_date = datetime.now(timezone.utc).date().isoformat()

    markdown = build_daily_markdown_report(
        daily_report=daily_report,
        paper_report=paper_report,
        scheduler_health=scheduler_health,
    )

    md_path = reports_path / f"daily_report_{final_report_date}.md"
    json_copy_path = reports_path / f"daily_report_{final_report_date}.json"

    md_path.write_text(markdown, encoding="utf-8")

    try:
        json_copy_path.write_text(
            json.dumps(daily_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    result = {
        "name": "DAILY_MARKDOWN_REPORT_WRITER",
        "status": "REPORT_WRITTEN",
        "report_date": final_report_date,
        "markdown_path": str(md_path),
        "json_copy_path": str(json_copy_path),
        "source_daily_report": str(daily_report_path),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    result_path = storage_path / "daily_markdown_report_result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result


def main() -> None:
    result = write_daily_markdown_report(storage_dir="storage")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()