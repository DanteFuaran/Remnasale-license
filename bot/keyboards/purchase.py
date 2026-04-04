from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


PRODUCTS = {
    "remnasale": {
        "name": "Remnasale",
        "emoji": "📦",
        "price": 15000,
        "description": "Бот для продажи VPN подписок",
    },
    "remnasup": {
        "name": "Remnasup",
        "emoji": "🛠",
        "price": 3000,
        "description": "Бот для поддержки клиентов",
    },
}

PURCHASE_DURATIONS = {
    "1m":  {"label": "1 месяц",    "months": 1},
    "3m":  {"label": "3 месяца",   "months": 3},
    "6m":  {"label": "6 месяцев",  "months": 6},
    "12m": {"label": "12 месяцев", "months": 12},
}


def _format_price(amount: int) -> str:
    if amount >= 1000:
        return f"{amount:,}".replace(",", " ")
    return str(amount)


def product_selection_kb(selected: set[str]) -> InlineKeyboardMarkup:
    buttons = []
    total = 0
    for key, product in PRODUCTS.items():
        is_selected = key in selected
        check = "✅" if is_selected else "☐"
        if is_selected:
            total += product["price"]
        buttons.append([
            InlineKeyboardButton(
                text=f"{product['emoji']} {product['name']}",
                callback_data=f"pt:{key}",
            ),
            InlineKeyboardButton(
                text=check,
                callback_data=f"pt:{key}",
            ),
        ])

    if selected:
        buttons.append([
            InlineKeyboardButton(
                text=f"Далее → ({_format_price(total)} ₽/мес)",
                callback_data="purchase_next_duration",
                style="success",
            ),
        ])

    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def purchase_duration_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, dur in PURCHASE_DURATIONS.items():
        buttons.append([
            InlineKeyboardButton(text=dur["label"], callback_data=f"pd:{key}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="purchase_start", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_method_kb(gateways: list[dict]) -> InlineKeyboardMarkup:
    from database import GATEWAY_TYPES
    buttons = []
    for gw in gateways:
        if not gw["is_active"]:
            continue
        gtype = gw["type"]
        meta = GATEWAY_TYPES.get(gtype, {})
        label = meta.get("label", gtype)
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"pm:{gtype}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="purchase_next_duration", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_link_kb(url: str, order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"pcheck:{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main", style="danger")],
    ])


def stars_payment_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pstars:{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main", style="danger")],
    ])
