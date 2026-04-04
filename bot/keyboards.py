from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone
from database import PERIODS


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
        return "🟢", expires.strftime("%d.%m.%Y")
    return "🟢", "♾ Бессрочно"


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список клиентов", callback_data="clients")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_menu")],
    ])


def clients_kb(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        emoji, _ = server_status(s)
        if not s["expires_at"]:
            expires_text = "♾"
        else:
            try:
                dt = datetime.fromisoformat(s["expires_at"])
                expires_text = dt.strftime("%d.%m.%Y")
            except Exception:
                expires_text = "—"
        row = [
            InlineKeyboardButton(text=s["name"], callback_data=f"s:{s['id']}"),
            InlineKeyboardButton(text=expires_text, callback_data=f"s:{s['id']}"),
            InlineKeyboardButton(text=emoji, callback_data=f"s:{s['id']}"),
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="➕ Добавить сервер", callback_data="add")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main")])
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
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="clients")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def server_detail_kb(server: dict) -> InlineKeyboardMarkup:
    sid = server["id"]
    is_active = server["is_active"]
    is_blacklisted = server.get("is_blacklisted", 0)

    row1 = [
        InlineKeyboardButton(text="🔄 Продлить", callback_data=f"ext:{sid}"),
        InlineKeyboardButton(text="🔓 Сбросить IP", callback_data=f"rip:{sid}"),
    ]

    toggle_text = "⏸ Приостановить" if is_active else "▶️ Возобновить"
    blk_text = "🔓 Разблокировать" if is_blacklisted else "🚫 Заблокировать"
    row2 = [
        InlineKeyboardButton(text=toggle_text, callback_data=f"tog:{sid}"),
        InlineKeyboardButton(text=blk_text, callback_data=f"blk:{sid}"),
    ]

    row3 = [
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ren:{sid}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{sid}"),
    ]

    row4 = [
        InlineKeyboardButton(text="🔙 Назад", callback_data="clients"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3, row4])


def confirm_delete_kb(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"cdel:{server_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"s:{server_id}"),
        ]
    ])


def backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Сохранить бэкап", callback_data="backup_save")],
        [InlineKeyboardButton(text="📤 Загрузить бэкап", callback_data="backup_load")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")],
    ])


def settings_kb(check_interval: int, offline_grace_days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🔄 Частота проверки: {check_interval} мин.",
            callback_data="settings_check_interval",
        )],
        [InlineKeyboardButton(
            text=f"📡 Автономность: {offline_grace_days} дн.",
            callback_data="settings_offline_grace",
        )],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="backup_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main")],
    ])
