from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def get_nested(data: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    current: Any = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def calculate_recent_watch_streak(rows: List[Dict[str, Any]]) -> int:
    streak = 0

    for row in reversed(rows):
        signal_side = str(row.get("signal_side", "UNKNOWN")).upper()

        if signal_side == "WATCH":
            streak += 1
        else:
            break

    return streak


def calculate_recent_average_score(rows: List[Dict[str, Any]], limit: int = 5) -> Optional[float]:
    recent_rows = rows[-limit:]
    scores: List[float] = []

    for row in recent_rows:
        score = safe_float(row.get("research_score"))
        if score is not None:
            scores.append(score)

    if not scores:
        return None

    return sum(scores) / len(scores)


def calculate_recent_average_confidence(rows: List[Dict[str, Any]], limit: int = 5) -> Optional[float]:
    recent_rows = rows[-limit:]
    confidences: List[float] = []

    for row in recent_rows:
        confidence = safe_float(row.get("signal_confidence"))
        if confidence is not None:
            confidences.append(confidence)

    if not confidences:
        return None

    return sum(confidences) / len(confidences)


def build_advice_text(report: Dict[str, Any]) -> str:
    recommendations = report.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []

    lines = [
        "[Signal Calibration Advisor]",
        "",
        f"Status: {report.get('status')}",
        f"Action: {report.get('recommended_action')}",
        f"Confidence: {report.get('advisor_confidence')}",
        f"Total Records: {report.get('total_records')}",
        f"Recent Watch Streak: {report.get('recent_watch_streak')}",
        f"Watch Ratio: {report.get('watch_ratio_pct')}%",
        f"Directional Ratio: {report.get('directional_ratio_pct')}%",
        f"Average Signal Confidence: {report.get('average_signal_confidence')}",
        f"Recent Average Research Score: {report.get('recent_average_research_score')}",
        "",
        "[Recommendations]",
    ]

    if recommendations:
        for item in recommendations:
            lines.append(f"- {item}")
    else:
        lines.append("- No recommendation.")

    lines.extend(
        [
            "",
            "[Important]",
            "This advisor only creates recommendations.",
            "It does not change trading logic or execute orders.",
        ]
    )

    return "\n".join(lines)


def evaluate_calibration(
    signal_quality_report: Dict[str, Any],
    performance_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_records = len(performance_history)

    status = str(signal_quality_report.get("status", "UNKNOWN"))
    overall_score = safe_int(signal_quality_report.get("overall_score"), 0)

    signal_distribution = get_nested(
        signal_quality_report,
        ["components", "signal_distribution"],
        {},
    )

    confidence_quality = get_nested(
        signal_quality_report,
        ["components", "confidence_quality"],
        {},
    )

    watch_ratio = safe_float(signal_distribution.get("watch_ratio_pct"), 0.0)
    directional_ratio = safe_float(signal_distribution.get("directional_ratio_pct"), 0.0)
    unknown_ratio = safe_float(signal_distribution.get("unknown_ratio_pct"), 0.0)

    avg_confidence = safe_float(confidence_quality.get("average_confidence"))
    recent_watch_streak = calculate_recent_watch_streak(performance_history)
    recent_avg_score = calculate_recent_average_score(performance_history, limit=5)
    recent_avg_confidence = calculate_recent_average_confidence(performance_history, limit=5)

    recommendations: List[str] = []
    recommended_action = "KEEP_CURRENT_RULES"
    advisor_confidence = "LOW"

    if total_records < 5:
        recommended_action = "COLLECT_MORE_DATA"
        advisor_confidence = "LOW"
        recommendations.append("Need at least 5 daily records before changing signal thresholds.")
        recommendations.append("Keep paper mode and continue daily collection.")

    else:
        advisor_confidence = "MEDIUM"

        if unknown_ratio > 0:
            recommended_action = "FIX_DATA_COMPLETENESS"
            recommendations.append("UNKNOWN signal records exist. Fix missing fields before changing strategy thresholds.")

        elif watch_ratio >= 90 and directional_ratio == 0:
            recommended_action = "RELAX_DIRECTIONAL_CONFIRMATION"
            recommendations.append("WATCH ratio is extremely high and no LONG/SHORT signals are being produced.")
            recommendations.append("Consider lowering directional confirmation requirements slightly.")
            recommendations.append("Do not lower risk controls such as invalidation or max position size.")

        elif watch_ratio >= 75 and directional_ratio < 20:
            recommended_action = "SLIGHTLY_RELAX_ENTRY_FILTERS"
            recommendations.append("WATCH ratio is high. Entry filters may be too conservative.")
            recommendations.append("Consider allowing conditional LONG/SHORT when research_score and confidence both improve.")

        elif directional_ratio >= 60 and overall_score < 60:
            recommended_action = "TIGHTEN_SIGNAL_FILTERS"
            recommendations.append("Directional signals are frequent while quality score is weak.")
            recommendations.append("Consider raising confidence threshold or requiring stronger confirmation.")

        elif avg_confidence is not None and avg_confidence < 0.45:
            recommended_action = "IMPROVE_CONFIDENCE_MODEL"
            recommendations.append("Average confidence is low. Improve confidence scoring before changing entry thresholds.")
            recommendations.append("Review how research_score, market_bias, OI, funding, and CVD are combined.")

        elif 20 <= directional_ratio <= 50 and overall_score >= 70:
            recommended_action = "KEEP_CURRENT_RULES"
            advisor_confidence = "HIGH"
            recommendations.append("Signal balance looks acceptable. Keep collecting data under current rules.")

        else:
            recommended_action = "MONITOR_ONLY"
            recommendations.append("No urgent calibration change is required yet.")
            recommendations.append("Continue paper mode and review after more records accumulate.")

    if recent_watch_streak >= 5:
        recommendations.append("Recent WATCH streak is long. Check whether confirmation logic is too strict.")

    if recent_avg_score is not None and 45 <= recent_avg_score <= 55:
        recommendations.append("Recent research_score is stuck near neutral. Metric weights may need better separation.")

    if recent_avg_confidence is not None and recent_avg_confidence < 0.5:
        recommendations.append("Recent confidence is below 0.50. Signal confidence may be too flat.")

    return {
        "name": "SIGNAL_CALIBRATION_ADVISOR",
        "status": "CALIBRATION_ADVICE_CREATED",
        "recommended_action": recommended_action,
        "advisor_confidence": advisor_confidence,
        "total_records": total_records,
        "signal_quality_status": status,
        "signal_quality_score": overall_score,
        "watch_ratio_pct": watch_ratio,
        "directional_ratio_pct": directional_ratio,
        "unknown_ratio_pct": unknown_ratio,
        "average_signal_confidence": avg_confidence,
        "recent_average_research_score": recent_avg_score,
        "recent_average_signal_confidence": recent_avg_confidence,
        "recent_watch_streak": recent_watch_streak,
        "recommendations": recommendations,
        "timestamp_utc": now_utc(),
    }


def create_signal_calibration_advice(
    storage_dir: str | Path = "storage",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    signal_quality_path = storage_path / "signal_quality_report.json"
    performance_history_path = storage_path / "performance_history.jsonl"

    output_json_path = storage_path / "signal_calibration_advice.json"
    output_text_path = storage_path / "signal_calibration_advice.txt"

    signal_quality_report = load_json_file(signal_quality_path)
    performance_history = load_jsonl(performance_history_path)

    if not signal_quality_report:
        result = {
            "name": "SIGNAL_CALIBRATION_ADVISOR",
            "status": "CALIBRATION_ADVICE_FAILED",
            "error": "signal_quality_report.json not found or empty.",
            "signal_quality_path": str(signal_quality_path),
            "timestamp_utc": now_utc(),
        }

        write_json_file(output_json_path, result)
        write_text_file(output_text_path, build_advice_text(result))
        return result

    result = evaluate_calibration(
        signal_quality_report=signal_quality_report,
        performance_history=performance_history,
    )

    result["source_signal_quality_report"] = str(signal_quality_path)
    result["source_performance_history"] = str(performance_history_path)
    result["output_json_path"] = str(output_json_path)
    result["output_text_path"] = str(output_text_path)

    write_json_file(output_json_path, result)
    write_text_file(output_text_path, build_advice_text(result))

    return result


def main() -> None:
    result = create_signal_calibration_advice(storage_dir="storage")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()