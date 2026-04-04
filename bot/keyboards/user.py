from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.keyboards.common import server_status


def user_main_menu_kb(support_url: str = "", community_url: str = "", is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🖥 Мои серверы", callback_data="my_servers")],
        [InlineKeyboardButton(text="➕ Добавить сервер", callback_data="purchase_start")],
    ]
    link_row = []
    if support_url:
        link_row.append(InlineKeyboardButton(text="🆘 Помощь", url=f"https://t.me/{support_url}"))
    if community_url:
        link_row.append(InlineKeyboardButton(text="👥 Сообщество", url=f"https://t.me/{community_url}"))
    if link_row:
        buttons.append(link_row)
    if is_admin:
        buttons.append([InlineKeyboardButton(text="🔑 Администрирование", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_servers_kb(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        emoji, _ = server_status(s)
        buttons.append([
            InlineKeyboardButton(text=f"{emoji} {s['name']}", callback_data=f"us:{s['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_server_kb(server: dict, support_url: str = "", community_url: str = "") -> InlineKeyboardMarkup:
    sid = server["id"]
    buttons = [
        [InlineKeyboardButton(text="🔄 Продлить", callback_data=f"uext:{sid}")],
    ]
    link_row = []
    if support_url:
        link_row.append(InlineKeyboardButton(text="🆘 Помощь", url=f"https://t.me/{support_url}"))
    if community_url:
        link_row.append(InlineKeyboardButton(text="👥 Сообщество", url=f"https://t.me/{community_url}"))
    if link_row:
        buttons.append(link_row)
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="my_servers", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_view_servers_kb(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        emoji, _ = server_status(s)
        buttons.append([
            InlineKeyboardButton(text=f"{emoji} {s['name']}", callback_data=f"us:{s['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="🔑 Администрирование", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_view_server_kb(server: dict, support_url: str = "", community_url: str = "") -> InlineKeyboardMarkup:
    sid = server["id"]
    buttons = [
        [InlineKeyboardButton(text="🔄 Продлить", callback_data=f"uext:{sid}")],
    ]
    link_row = []
    if support_url:
        link_row.append(InlineKeyboardButton(text="🆘 Помощь", url=f"https://t.me/{support_url}"))
    if community_url:
        link_row.append(InlineKeyboardButton(text="👥 Сообщество", url=f"https://t.me/{community_url}"))
    if link_row:
        buttons.append(link_row)
    buttons.append([InlineKeyboardButton(text="🔑 Администрирование", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_view_empty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Администрирование", callback_data="main")],
    ])
