from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone

PERIOD_LABELS = {
    "1m": "1 месяц",
    "3m": "3 месяца",
    "6m": "6 месяцев",
    "12m": "12 месяцев",
    "unlimited": "Безлимитный",
}


def server_status(server: dict) -> tuple[str, str]:
    if server.get("is_blacklisted"):
        return "❌", "Заблокирован"
    if not server["is_active"]:
        return "🔴", "Приостановлен"
    if server["expires_at"]:
        expires = datetime.fromisoformat(server["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return "🟡", "Истёк"
    return "🟢", "Активен"
