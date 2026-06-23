from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
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


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100, 2)


def count_by_key(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in rows:
        value = str(row.get(key, "UNKNOWN")).upper()
        counts[value] = counts.get(value, 0) + 1

    return counts


def evaluate_signal_distribution(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    signal_counts = count_by_key(rows, "signal_side")

    watch_count = signal_counts.get("WATCH", 0)
    long_count = signal_counts.get("LONG", 0)
    short_count = signal_counts.get("SHORT", 0)
    unknown_count = signal_counts.get("UNKNOWN", 0)

    directional_count = long_count + short_count

    watch_ratio = pct(watch_count, total)
    directional_ratio = pct(directional_count, total)
    unknown_ratio = pct(unknown_count, total)

    score = 100
    notes: List[str] = []

    if total < 5:
        score -= 25
        notes.append("History sample is still too small. Need at least 5 records.")

    if watch_ratio > 90:
        score -= 25
        notes.append("WATCH ratio is extremely high. Signal logic may be too conservative.")
    elif watch_ratio > 75:
        score -= 15
        notes.append("WATCH ratio is high. More directional confirmation logic may be needed.")

    if directional_ratio == 0 and total >= 5:
        score -= 20
        notes.append("No LONG/SHORT signals detected yet.")

    if unknown_ratio > 0:
        score -= 10
        notes.append("UNKNOWN signals detected. Some records may be incomplete.")

    score = max(0, min(100, score))

    return {
        "name": "SIGNAL_DISTRIBUTION",
        "score": score,
        "total_records": total,
        "signal_counts": signal_counts,
        "watch_ratio_pct": watch_ratio,
        "directional_ratio_pct": directional_ratio,
        "unknown_ratio_pct": unknown_ratio,
        "notes": notes,
    }


def evaluate_score_signal_alignment(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Checks whether research_score roughly aligns with signal_side.

    Expected:
    - high score should not always remain WATCH forever
    - very low score should not produce LONG
    - confidence should not be missing
    """
    total = len(rows)
    usable = 0
    violations = 0
    notes: List[str] = []

    high_score_watch = 0
    low_score_long = 0
    high_score_short = 0

    for row in rows:
        signal_side = str(row.get("signal_side", "UNKNOWN")).upper()
        score = safe_float(row.get("research_score"))

        if score is None:
            continue

        usable += 1

        if score >= 70 and signal_side == "WATCH":
            high_score_watch += 1
            violations += 1

        if score <= 35 and signal_side == "LONG":
            low_score_long += 1
            violations += 1

        if score >= 65 and signal_side == "SHORT":
            high_score_short += 1
            violations += 1

    if usable == 0:
        return {
            "name": "SCORE_SIGNAL_ALIGNMENT",
            "score": 50,
            "usable_records": 0,
            "violations": 0,
            "notes": ["No usable research_score records found."],
        }

    violation_ratio = violations / usable

    score = 100 - int(violation_ratio * 100)

    if high_score_watch > 0:
        notes.append("High research_score sometimes remains WATCH. This may be acceptable during conditional mode, but should be monitored.")

    if low_score_long > 0:
        notes.append("Low research_score produced LONG. This is a potential logic issue.")

    if high_score_short > 0:
        notes.append("High research_score produced SHORT. This may indicate score direction is not clearly defined.")

    score = max(0, min(100, score))

    return {
        "name": "SCORE_SIGNAL_ALIGNMENT",
        "score": score,
        "total_records": total,
        "usable_records": usable,
        "violations": violations,
        "violation_ratio_pct": round(violation_ratio * 100, 2),
        "high_score_watch": high_score_watch,
        "low_score_long": low_score_long,
        "high_score_short": high_score_short,
        "notes": notes,
    }


def evaluate_confidence_quality(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    confidences: List[float] = []

    for row in rows:
        value = safe_float(row.get("signal_confidence"))
        if value is not None:
            confidences.append(value)

    if not confidences:
        return {
            "name": "CONFIDENCE_QUALITY",
            "score": 50,
            "average_confidence": None,
            "min_confidence": None,
            "max_confidence": None,
            "notes": ["No confidence values found."],
        }

    avg_conf = sum(confidences) / len(confidences)
    min_conf = min(confidences)
    max_conf = max(confidences)

    score = 100
    notes: List[str] = []

    if avg_conf < 0.45:
        score -= 25
        notes.append("Average confidence is low.")
    elif avg_conf < 0.55:
        score -= 10
        notes.append("Average confidence is moderate-low.")

    if max_conf <= 0.55 and len(confidences) >= 5:
        score -= 15
        notes.append("Confidence never rises meaningfully. Signal engine may be too flat.")

    score = max(0, min(100, score))

    return {
        "name": "CONFIDENCE_QUALITY",
        "score": score,
        "usable_records": len(confidences),
        "average_confidence": round(avg_conf, 4),
        "min_confidence": round(min_conf, 4),
        "max_confidence": round(max_conf, 4),
        "notes": notes,
    }


def evaluate_system_stability(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)

    if total == 0:
        return {
            "name": "SYSTEM_STABILITY",
            "score": 0,
            "notes": ["No history records found."],
        }

    healthy_count = 0
    dry_run_passed_count = 0
    telegram_sent_or_disabled_count = 0

    for row in rows:
        scheduler_status = str(row.get("scheduler_status", "UNKNOWN")).upper()
        dry_run_status = str(row.get("operational_dry_run", "UNKNOWN")).upper()
        telegram_status = str(row.get("telegram_daily_send", "UNKNOWN")).upper()

        if scheduler_status == "HEALTHY":
            healthy_count += 1

        if dry_run_status in {"PASSED", "PASS", "OK", "SUCCESS", "COMPLETED"}:
            dry_run_passed_count += 1

        if telegram_status in {"SENT", "DISABLED", "OK", "SUCCESS", "COMPLETED"}:
            telegram_sent_or_disabled_count += 1

    healthy_ratio = healthy_count / total
    dry_run_ratio = dry_run_passed_count / total
    telegram_ratio = telegram_sent_or_disabled_count / total

    score = int(((healthy_ratio + dry_run_ratio + telegram_ratio) / 3) * 100)

    notes: List[str] = []

    if healthy_ratio < 1:
        notes.append("Some records were not HEALTHY.")
    if dry_run_ratio < 1:
        notes.append("Some operational dry runs were not PASSED.")
    if telegram_ratio < 1:
        notes.append("Some Telegram sends failed or were unknown.")

    return {
        "name": "SYSTEM_STABILITY",
        "score": score,
        "total_records": total,
        "healthy_ratio_pct": round(healthy_ratio * 100, 2),
        "dry_run_passed_ratio_pct": round(dry_run_ratio * 100, 2),
        "telegram_ok_ratio_pct": round(telegram_ratio * 100, 2),
        "notes": notes,
    }


def build_text_report(report: Dict[str, Any]) -> str:
    lines = [
        "[Signal Quality Report]",
        "",
        f"Status: {report.get('status')}",
        f"Overall Score: {report.get('overall_score')}/100",
        f"Total Records: {report.get('total_records')}",
        f"Latest Report Date: {report.get('latest_report_date')}",
        "",
        "[Component Scores]",
    ]

    components = report.get("components", {})

    for key, value in components.items():
        lines.append(f"- {key}: {value.get('score')}/100")

    lines.extend(
        [
            "",
            "[Signal Distribution]",
            json.dumps(components.get("signal_distribution", {}), ensure_ascii=False, indent=2),
            "",
            "[Score Signal Alignment]",
            json.dumps(components.get("score_signal_alignment", {}), ensure_ascii=False, indent=2),
            "",
            "[Confidence Quality]",
            json.dumps(components.get("confidence_quality", {}), ensure_ascii=False, indent=2),
            "",
            "[System Stability]",
            json.dumps(components.get("system_stability", {}), ensure_ascii=False, indent=2),
        ]
    )

    return "\n".join(lines)


def evaluate_signal_quality(
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    history_path = storage_path / "performance_history.jsonl"
    report_path = storage_path / "signal_quality_report.json"
    text_path = storage_path / "signal_quality_report.txt"

    rows = load_jsonl(history_path)

    signal_distribution = evaluate_signal_distribution(rows)
    score_signal_alignment = evaluate_score_signal_alignment(rows)
    confidence_quality = evaluate_confidence_quality(rows)
    system_stability = evaluate_system_stability(rows)

    component_scores = [
        signal_distribution["score"],
        score_signal_alignment["score"],
        confidence_quality["score"],
        system_stability["score"],
    ]

    overall_score = int(sum(component_scores) / len(component_scores)) if component_scores else 0

    if overall_score >= 85:
        status = "QUALITY_STRONG"
    elif overall_score >= 70:
        status = "QUALITY_OK"
    elif overall_score >= 50:
        status = "QUALITY_NEEDS_MORE_DATA"
    else:
        status = "QUALITY_WEAK"

    latest_report_date = rows[-1].get("report_date") if rows else None

    report = {
        "name": "SIGNAL_QUALITY_EVALUATOR",
        "status": status,
        "overall_score": overall_score,
        "total_records": len(rows),
        "latest_report_date": latest_report_date,
        "components": {
            "signal_distribution": signal_distribution,
            "score_signal_alignment": score_signal_alignment,
            "confidence_quality": confidence_quality,
            "system_stability": system_stability,
        },
        "history_path": str(history_path),
        "report_path": str(report_path),
        "text_path": str(text_path),
        "timestamp_utc": now_utc(),
    }

    write_json_file(report_path, report)
    write_text_file(text_path, build_text_report(report))

    return report


def main() -> None:
    result = evaluate_signal_quality(storage_dir="storage")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()