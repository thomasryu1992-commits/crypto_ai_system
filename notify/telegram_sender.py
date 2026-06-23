from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")


# ============================================================
# Console Safety
# ============================================================

def configure_utf8_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(value: Any = "") -> None:
    text = "" if value is None else str(value)

    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="backslashreplace").decode(
            encoding,
            errors="replace",
        )
        print(safe_text)


configure_utf8_console()


# ============================================================
# Basic Helpers
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env_file(env_path: Optional[Path] = None) -> Dict[str, str]:
    path = env_path or (PROJECT_ROOT / ".env")
    values: Dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            values[key] = value
            os.environ.setdefault(key, value)

    return values


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "enabled",
    }


def load_text_file(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8", errors="replace")


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mask_token(token: Optional[str]) -> str:
    if not token:
        return ""

    if len(token) <= 10:
        return "***"

    return token[:6] + "..." + token[-4:]


def get_telegram_config() -> Dict[str, Any]:
    load_env_file()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    enabled = env_bool("ENABLE_TELEGRAM", default=True)

    return {
        "enabled": enabled,
        "bot_token": bot_token,
        "bot_token_masked": mask_token(bot_token),
        "chat_id": chat_id,
        "has_token": bool(bot_token),
        "has_chat_id": bool(chat_id),
    }


# ============================================================
# Telegram Sender
# ============================================================

def send_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    disable_web_page_preview: bool = True,
    timeout_seconds: int = 20,
) -> Dict[str, Any]:
    """
    Common Telegram sender.

    This is the shared function used by:
    1. daily report sender
    2. legacy alert sender
    3. any future Telegram notification
    """
    load_env_file()

    final_bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    final_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not message or not message.strip():
        return {
            "ok": False,
            "status": "MESSAGE_EMPTY",
            "error": "Telegram message is empty.",
            "timestamp_utc": now_utc(),
        }

    if not final_bot_token:
        return {
            "ok": False,
            "status": "TOKEN_MISSING",
            "error": "TELEGRAM_BOT_TOKEN is missing.",
            "timestamp_utc": now_utc(),
        }

    if not final_chat_id:
        return {
            "ok": False,
            "status": "CHAT_ID_MISSING",
            "error": "TELEGRAM_CHAT_ID is missing.",
            "timestamp_utc": now_utc(),
        }

    url = f"https://api.telegram.org/bot{final_bot_token}/sendMessage"

    payload = {
        "chat_id": final_chat_id,
        "text": message,
        "disable_web_page_preview": "true" if disable_web_page_preview else "false",
    }

    encoded_payload = urllib.parse.urlencode(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=encoded_payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = response.getcode()

        try:
            parsed_body = json.loads(response_body)
        except Exception:
            parsed_body = {"raw": response_body}

        telegram_ok = bool(parsed_body.get("ok")) if isinstance(parsed_body, dict) else False

        return {
            "ok": telegram_ok,
            "status": "SENT" if telegram_ok else "SEND_FAILED",
            "http_status_code": status_code,
            "telegram_response": parsed_body,
            "timestamp_utc": now_utc(),
        }

    except Exception as exc:
        return {
            "ok": False,
            "status": "SEND_EXCEPTION",
            "error": str(exc),
            "traceback": traceback.format_exc()[-4000:],
            "timestamp_utc": now_utc(),
        }


def send_telegram_message(message: str) -> Dict[str, Any]:
    """
    Backward-compatible wrapper.
    Existing code may already call send_telegram_message(message).
    """
    return send_message(message=message)


def send_telegram_alert(message: str) -> Dict[str, Any]:
    """
    Backward-compatible wrapper for old alert style.
    """
    return send_message(message=message)


# ============================================================
# Daily Report Sender
# ============================================================

def send_daily_report_from_file(
    storage_dir: str | Path = STORAGE_DIR,
    message_filename: str = "telegram_daily_report_message.txt",
    result_filename: str = "telegram_daily_report_send_result.json",
) -> Dict[str, Any]:
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    message_path = storage_path / message_filename
    result_path = storage_path / result_filename

    config = get_telegram_config()
    message = load_text_file(message_path)

    if not config["enabled"]:
        result = {
            "name": "TELEGRAM_DAILY_REPORT_SENDER",
            "status": "DISABLED",
            "ok": True,
            "message_path": str(message_path),
            "message_length": len(message),
            "config": {
                "enabled": config["enabled"],
                "has_token": config["has_token"],
                "has_chat_id": config["has_chat_id"],
                "bot_token_masked": config["bot_token_masked"],
            },
            "timestamp_utc": now_utc(),
        }

        write_json_file(result_path, result)
        return result

    if not message.strip():
        result = {
            "name": "TELEGRAM_DAILY_REPORT_SENDER",
            "status": "MESSAGE_EMPTY",
            "ok": False,
            "message_path": str(message_path),
            "message_length": len(message),
            "config": {
                "enabled": config["enabled"],
                "has_token": config["has_token"],
                "has_chat_id": config["has_chat_id"],
                "bot_token_masked": config["bot_token_masked"],
            },
            "timestamp_utc": now_utc(),
        }

        write_json_file(result_path, result)
        return result

    send_result = send_message(
        message=message,
        bot_token=config["bot_token"],
        chat_id=config["chat_id"],
    )

    result = {
        "name": "TELEGRAM_DAILY_REPORT_SENDER",
        "status": send_result.get("status", "UNKNOWN"),
        "ok": send_result.get("ok", False),
        "message_path": str(message_path),
        "message_length": len(message),
        "config": {
            "enabled": config["enabled"],
            "has_token": config["has_token"],
            "has_chat_id": config["has_chat_id"],
            "bot_token_masked": config["bot_token_masked"],
            "chat_id": config["chat_id"],
        },
        "send_result": send_result,
        "timestamp_utc": now_utc(),
    }

    write_json_file(result_path, result)
    return result


def send_daily_report_message(storage_dir: str | Path = STORAGE_DIR) -> Dict[str, Any]:
    """
    Alias for future compatibility.
    """
    return send_daily_report_from_file(storage_dir=storage_dir)


# ============================================================
# Main
# ============================================================

def main() -> None:
    result = send_daily_report_from_file(storage_dir=STORAGE_DIR)
    safe_print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()