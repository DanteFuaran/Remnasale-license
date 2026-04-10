from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from bot.keyboards.common import server_status


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список клиентов", callback_data="clients")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary")],
    ])


def clients_kb(servers: list[dict], silent_ids: set[int] | None = None) -> InlineKeyboardMarkup:
    buttons = []
    _silent = silent_ids or set()
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
        name = f"⚠️ {s['name']}" if s["id"] in _silent else s["name"]
        if not s.get("server_ip"):
            name = f"❗{name}"
        row = [
            InlineKeyboardButton(text=name, callback_data=f"s:{s['id']}"),
            InlineKeyboardButton(text=expires_text, callback_data=f"ext:{s['id']}"),
            InlineKeyboardButton(text=emoji, callback_data=f"tgl:{s['id']}"),
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="➕ Добавить сервер", callback_data="add")])
    buttons.append([InlineKeyboardButton(text="📢 Написать всем", callback_data="broadcast")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel", style="primary")])
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
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
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
    is_muted = server.get("is_muted", 0)

    toggle_text = "⏸ Приостановить" if is_active else "▶️ Возобновить"
    blk_text = "🔓 Разблокировать" if is_blacklisted else "🚫 Заблокировать"
    mute_text = "🔊 Разглушить" if is_muted else "🔇 Заглушить"
    donate_muted = server.get("donate_muted", 0)
    donate_text = "🔴 Донаты" if donate_muted else "🟢 Донаты"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Показать ключ", callback_data=f"showkey:{sid}")],
        [
            InlineKeyboardButton(text="🔄 Продлить",   callback_data=f"ext:{sid}"),
            InlineKeyboardButton(text=toggle_text,     callback_data=f"tog:{sid}"),
        ],
        [InlineKeyboardButton(text="✉️ Написать сообщение", callback_data=f"msg:{sid}")],
        [
            InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ren:{sid}"),
            InlineKeyboardButton(text="🔓 Сбросить IP",  callback_data=f"rip:{sid}"),
        ],
        [
            InlineKeyboardButton(text=mute_text, callback_data=f"mute:{sid}"),
            InlineKeyboardButton(text=donate_text, callback_data=f"dmute:{sid}"),
        ],
        [
            InlineKeyboardButton(text=blk_text,       callback_data=f"blk:{sid}", style="danger"),
            InlineKeyboardButton(text="🗑 Удалить",    callback_data=f"del:{sid}", style="danger"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад",        callback_data="clients", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
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
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
