from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone
from database import PERIODS


def server_status(server: dict) -> tuple[str, str]:
    if not server["is_active"]:
        return "🔴", "Приостановлен"

    if server["expires_at"]:
        expires = datetime.fromisoformat(server["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return "🟡", "Истёк"
        return "🟢", expires.strftime("%d.%m.%Y")

    return "🟢", "♾ Бессрочно"


def main_menu_kb(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        emoji, status = server_status(s)
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {s['name']} | {status}",
            callback_data=f"s:{s['id']}",
        )])

    buttons.append([InlineKeyboardButton(
        text="➕ Добавить сервер",
        callback_data="add",
    )])

    buttons.append([InlineKeyboardButton(
        text="⚙️ Администрирование",
        callback_data="admin",
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def period_kb(prefix: str = "ap") -> InlineKeyboardMarkup:
    labels = {
        "1m": "1 месяц",
        "3m": "3 месяца",
        "6m": "6 месяцев",
        "12m": "12 месяцев",
        "unlimited": "♾ Бессрочно",
    }
    buttons = []
    for key, label in labels.items():
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"{prefix}:{key}",
        )])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def server_detail_kb(server: dict) -> InlineKeyboardMarkup:
    sid = server["id"]
    is_active = server["is_active"]

    row1 = [
        InlineKeyboardButton(text="🔄 Продлить", callback_data=f"ext:{sid}"),
        InlineKeyboardButton(text="🔓 Сбросить IP", callback_data=f"rip:{sid}"),
    ]

    toggle_text = "⏸ Приостановить" if is_active else "▶️ Возобновить"
    row2 = [InlineKeyboardButton(text=toggle_text, callback_data=f"tog:{sid}")]

    row3 = [
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ren:{sid}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{sid}"),
    ]

    row4 = [InlineKeyboardButton(text="🔙 Назад", callback_data="main")]

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3, row4])


def confirm_delete_kb(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"cdel:{server_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"s:{server_id}"),
        ]
    ])


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="backup_menu")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main")],
    ])


def backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Сохранить", callback_data="backup_save")],
        [InlineKeyboardButton(text="📤 Загрузить", callback_data="backup_load")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
    ])


def settings_kb(check_interval: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🔄 Частота проверки: {check_interval} мин.",
            callback_data="settings_check_interval",
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")],
    ])
