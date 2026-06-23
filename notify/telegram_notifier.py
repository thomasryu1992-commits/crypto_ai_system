from __future__ import annotations

from typing import Any

import requests

from config.settings import settings
from core.time_utils import utc_now_iso


def send_telegram_message(message: str) -> dict[str, Any]:
    if not settings.telegram_enabled or not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {
            "status": "DRY_RUN_SENT",
            "generated_at": utc_now_iso(),
            "reason": "Telegram disabled or credentials missing.",
            "message_preview": message[:500],
        }

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        return {
            "status": "SENT" if response.status_code == 200 else "FAILED",
            "status_code": response.status_code,
            "response_text": response.text[:500],
            "generated_at": utc_now_iso(),
        }
    except Exception as exc:
        return {"status": "FAILED", "error": str(exc), "generated_at": utc_now_iso()}
