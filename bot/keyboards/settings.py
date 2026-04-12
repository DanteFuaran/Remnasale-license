from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton


def setting_edit_kb(clear_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_cb, style="danger")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb, style="danger")],
    ])


def setting_edit_pending_kb(accept_cb: str, clear_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_cb, style="danger")],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb, style="danger"),
            InlineKeyboardButton(text="✅ Принять", callback_data=accept_cb, style="success"),
        ],
    ])


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Настройка синхронизации", callback_data="settings_sync")],
        [InlineKeyboardButton(text="🌐 Домен лиц. сервера", callback_data="settings_license_host")],
        [
            InlineKeyboardButton(text="🆘 Помощь", callback_data="settings_support_url"),
            InlineKeyboardButton(text="👥 Сообщество", callback_data="settings_community_url"),
        ],
        [
            InlineKeyboardButton(text="💳 Платёжные системы", callback_data="settings_payments"),
            InlineKeyboardButton(text="💝 Донаты", callback_data="settings_donate"),
        ],
        [InlineKeyboardButton(text="💾 Управление БД", callback_data="backup_menu")],
        [InlineKeyboardButton(text="🎨 Брендирование", callback_data="branding_menu")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ])


def donate_kb(enabled: bool, btn1: dict, btn2: dict, btn3: dict) -> InlineKeyboardMarkup:
    toggle_text = "🟢 Включен" if enabled else "🔴 Выключен"
    rows = [
        [InlineKeyboardButton(text=toggle_text, callback_data="donate_toggle")],
        [InlineKeyboardButton(text="📝 Настроить сообщение", callback_data="donate_edit_message")],
        [
            InlineKeyboardButton(
                text=f"{'🟢' if btn1.get('enabled') else '🔴'} {btn1.get('label') or 'Кнопка 1'}",
                callback_data="donate_btn_1",
            ),
            InlineKeyboardButton(
                text=f"{'🟢' if btn2.get('enabled') else '🔴'} {btn2.get('label') or 'Кнопка 2'}",
                callback_data="donate_btn_2",
            ),
            InlineKeyboardButton(
                text=f"{'🟢' if btn3.get('enabled') else '🔴'} {btn3.get('label') or 'Кнопка 3'}",
                callback_data="donate_btn_3",
            ),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_btn_kb(idx: int, btn: dict) -> InlineKeyboardMarkup:
    toggle = "🟢 Включен" if btn.get("enabled") else "🔴 Выключен"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle, callback_data=f"donate_btn_{idx}_toggle")],
        [
            InlineKeyboardButton(text="✏️ Название", callback_data=f"donate_btn_{idx}_label"),
            InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"donate_btn_{idx}_url"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_donate", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ])


def branding_kb(has_banner: bool = False) -> InlineKeyboardMarkup:
    action_text = "🖼 Изменить банер" if has_banner else "➕ Установить банер"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=action_text, callback_data="branding_change_banner")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
        ],
    ])


def sync_kb(check_interval: int, offline_grace_days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🔄 Частота проверки: {check_interval} мин.",
            callback_data="settings_check_interval",
        )],
        [InlineKeyboardButton(
            text=f"📡 Автономность: {offline_grace_days} дн.",
            callback_data="settings_offline_grace",
        )],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
        ],
    ])


def backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настройки автобэкапа", callback_data="autobackup_menu")],
        [
            InlineKeyboardButton(text="📥 Сохранить", callback_data="backup_save"),
            InlineKeyboardButton(text="📤 Загрузить", callback_data="backup_load"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu", style="primary"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
        ],
    ])


FREQ_LABELS = {
    "hourly": "⏱ Каждый час",
    "daily": "📅 Раз в день",
    "weekly": "📆 Раз в неделю",
    "monthly": "🗓 Раз в месяц",
}


def autobackup_settings_kb(settings: dict) -> InlineKeyboardMarkup:
    enabled = settings.get("enabled") == "1"
    silent = settings.get("silent_mode") == "1"

    toggle_text = "🟢" if enabled else "🔴"
    silent_text = "🟢" if silent else "🔴"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Автобэкап", callback_data="autobackup_toggle"),
            InlineKeyboardButton(text=toggle_text, callback_data="autobackup_toggle"),
        ],
        [
            InlineKeyboardButton(text="Тихий режим", callback_data="autobackup_silent"),
            InlineKeyboardButton(text=silent_text, callback_data="autobackup_silent"),
        ],
        [
            InlineKeyboardButton(text="🤖 Токен бота", callback_data="autobackup_set_token"),
            InlineKeyboardButton(text="💬 ID Получателя", callback_data="autobackup_set_chat"),
        ],
        [InlineKeyboardButton(text="🕐 Частота отправки", callback_data="autobackup_set_freq")],
        [InlineKeyboardButton(text="📤 Отправить бэкап сейчас", callback_data="autobackup_force")],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_cancel", style="danger"),
            InlineKeyboardButton(text="✅ Принять", callback_data="autobackup_accept", style="success"),
        ],
    ])


def autobackup_freq_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, label in FREQ_LABELS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"abfreq:{key}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_menu", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payments_kb(gateways: list[dict]) -> InlineKeyboardMarkup:
    from database import GATEWAY_TYPES
    buttons = []
    for gw in gateways:
        gtype = gw["type"]
        meta = GATEWAY_TYPES.get(gtype, {})
        label = meta.get("label", gtype)
        status = "🟢" if gw["is_active"] else "🔴"
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"gw:{gtype}"),
            InlineKeyboardButton(text="🐞 Тест", callback_data=f"gwtest:{gtype}"),
            InlineKeyboardButton(text=status, callback_data=f"gwt:{gtype}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="🔢 Изменить позиционирование", callback_data="gw_placement"),
    ])
    buttons.append([
        InlineKeyboardButton(text="💸 Валюта по умолчанию", callback_data="gw_currency"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu", style="primary"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


_REQUIRES_WEBHOOK = {"yoomoney", "stars"}


def gateway_detail_kb(gw: dict, public_url: str = "") -> InlineKeyboardMarkup:
    from database import GATEWAY_TYPES
    gtype = gw["type"]
    meta = GATEWAY_TYPES.get(gtype, {})
    fields = meta.get("fields", {})

    buttons = []
    field_items = list(fields.items())
    for i in range(0, len(field_items), 2):
        row = []
        for field_key, field_label in field_items[i:i+2]:
            row.append(InlineKeyboardButton(
                text=field_label,
                callback_data=f"gwf:{gtype}:{field_key}",
            ))
        buttons.append(row)

    if gtype in _REQUIRES_WEBHOOK and public_url:
        webhook_url = f"{public_url.rstrip('/')}/api/v1/webhook/{gtype}"
        buttons.append([InlineKeyboardButton(
            text="📋 Скопировать вебхук",
            copy_text=CopyTextButton(text=webhook_url),
        )])

    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_payments", style="primary"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


CURRENCIES = ["RUB", "USD", "EUR"]

CURRENCY_LABELS = {
    "RUB": "🇷🇺 RUB — Рубль",
    "USD": "🇺🇸 USD — Доллар",
    "EUR": "🇪🇺 EUR — Евро",
}


def gateway_placement_kb(gateways: list[dict]) -> InlineKeyboardMarkup:
    from database import GATEWAY_TYPES
    buttons = []
    for idx, gw in enumerate(gateways):
        gtype = gw["type"]
        meta = GATEWAY_TYPES.get(gtype, {})
        label = meta.get("label", gtype)
        row = [InlineKeyboardButton(text=label, callback_data=f"gwpos:{gtype}")]
        arrow_cb = f"gwup:{gtype}" if idx > 0 else "gwup_noop"
        row.append(InlineKeyboardButton(text="⬆️", callback_data=arrow_cb))
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_payments", style="primary"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def gateway_currency_kb(current: str) -> InlineKeyboardMarkup:
    buttons = []
    for cur in CURRENCIES:
        mark = "✅ " if cur == current else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{CURRENCY_LABELS[cur]}",
            callback_data=f"gwcur:{cur}",
        )])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_payments", style="primary"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
