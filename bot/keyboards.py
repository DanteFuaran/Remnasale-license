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
            InlineKeyboardButton(text=expires_text, callback_data=f"ext:{s['id']}"),
            InlineKeyboardButton(text=emoji, callback_data=f"tgl:{s['id']}"),
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="➕ Добавить сервер", callback_data="add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def period_kb(prefix: str = "ap", back_cb: str = "clients") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 месяц",    callback_data=f"{prefix}:1m"),
            InlineKeyboardButton(text="3 месяца",   callback_data=f"{prefix}:3m"),
        ],
        [
            InlineKeyboardButton(text="6 месяцев",  callback_data=f"{prefix}:6m"),
            InlineKeyboardButton(text="12 месяцев", callback_data=f"{prefix}:12m"),
        ],
        [
            InlineKeyboardButton(text="♾", callback_data=f"{prefix}:unlimited"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад",      callback_data=back_cb, style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ])


def add_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 месяц",    callback_data="ap:1m"),
            InlineKeyboardButton(text="3 месяца",   callback_data="ap:3m"),
        ],
        [
            InlineKeyboardButton(text="6 месяцев",  callback_data="ap:6m"),
            InlineKeyboardButton(text="12 месяцев", callback_data="ap:12m"),
        ],
        [
            InlineKeyboardButton(text="♾", callback_data="ap:unlimited"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add", style="danger"),
        ],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add", style="danger")],
    ])


def server_detail_kb(server: dict) -> InlineKeyboardMarkup:
    sid = server["id"]
    is_active = server["is_active"]
    is_blacklisted = server.get("is_blacklisted", 0)

    toggle_text = "⏸ Приостановить" if is_active else "▶️ Возобновить"
    blk_text = "🔓 Разблокировать" if is_blacklisted else "🚫 Заблокировать"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Продлить",   callback_data=f"ext:{sid}", style="primary"),
            InlineKeyboardButton(text=toggle_text,     callback_data=f"tog:{sid}"),
        ],
        [InlineKeyboardButton(text="✉️ Написать сообщение", callback_data=f"msg:{sid}")],
        [
            InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ren:{sid}"),
            InlineKeyboardButton(text="🔓 Сбросить IP",  callback_data=f"rip:{sid}"),
        ],
        [
            InlineKeyboardButton(text=blk_text,       callback_data=f"blk:{sid}", style="danger"),
            InlineKeyboardButton(text="🗑 Удалить",    callback_data=f"del:{sid}", style="danger"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад",        callback_data="clients", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ])


def compose_kb(server_id: int, has_text: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Ввести текст", callback_data=f"cmt:{server_id}")],
    ]
    if has_text:
        buttons.append([
            InlineKeyboardButton(text="👁 Предпросмотр", callback_data=f"cmp:{server_id}"),
            InlineKeyboardButton(text="📤 Отправить", callback_data=f"cms:{server_id}", style="success"),
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"s:{server_id}", style="primary"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_servers_kb(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        emoji, _ = server_status(s)
        buttons.append([
            InlineKeyboardButton(text=f"{emoji} {s['name']}", callback_data=f"us:{s['id']}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_server_kb(server: dict, support_url: str = "", community_url: str = "") -> InlineKeyboardMarkup:
    sid = server["id"]
    buttons = [
        [InlineKeyboardButton(text="🔄 Продлить", callback_data=f"uext:{sid}", style="primary")],
    ]
    link_row = []
    if support_url:
        link_row.append(InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{support_url}"))
    if community_url:
        link_row.append(InlineKeyboardButton(text="👥 Сообщество", url=f"https://t.me/{community_url}"))
    if link_row:
        buttons.append(link_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def setting_edit_kb(current: str, clear_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_cb, style="danger")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb, style="primary")],
    ])


def backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Сохранить бэкап", callback_data="backup_save")],
        [InlineKeyboardButton(text="📤 Загрузить бэкап", callback_data="backup_load")],
        [InlineKeyboardButton(text="⬅️ Назад",           callback_data="settings_menu", style="primary")],
    ])


def settings_kb(check_interval: int, offline_grace_days: int,
                support_url: str = "", community_url: str = "") -> InlineKeyboardMarkup:
    support_display = support_url or "Не указана"
    community_display = community_url or "Не указано"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🔄 Частота проверки: {check_interval} мин.",
            callback_data="settings_check_interval",
        )],
        [InlineKeyboardButton(
            text=f"📡 Автономность: {offline_grace_days} дн.",
            callback_data="settings_offline_grace",
        )],
        [InlineKeyboardButton(
            text=f"🆘 Поддержка: {support_display}",
            callback_data="settings_support_url",
        )],
        [InlineKeyboardButton(
            text=f"👥 Сообщество: {community_display}",
            callback_data="settings_community_url",
        )],
        [InlineKeyboardButton(text="💳 Платёжные системы", callback_data="settings_payments")],
        [InlineKeyboardButton(text="💾 Бэкап",            callback_data="backup_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню",     callback_data="main", style="primary")],
    ])
