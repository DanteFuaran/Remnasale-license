from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


PRODUCTS = {
    "remnasale": {
        "name": "Remnasale",
        "emoji": "📦",
        "price": 15000,          # безлимит (единоразово)
        "price_monthly": 1500,   # ежемесячная подписка
        "description": "Телеграм бот для продажи и управления подписками.",
    },
    "remnasup": {
        "name": "Remnasup",
        "emoji": "🚨",
        "price": 3000,           # безлимит (единоразово)
        "price_monthly": 500,    # ежемесячная подписка
        "description": "Телеграм бот для поддержки пользователей.",
    },
}

PURCHASE_DURATIONS = {
    "1m":        {"label": "1 месяц",     "months": 1},
    "3m":        {"label": "3 месяца",    "months": 3},
    "6m":        {"label": "6 месяцев",   "months": 6},
    "12m":       {"label": "12 месяцев",  "months": 12},
    "unlimited": {"label": "Безлимит",   "months": None},
}


def _format_price(amount: int) -> str:
    if amount >= 1000:
        return f"{amount:,}".replace(",", " ")
    return str(amount)


def product_selection_kb(selected: set[str]) -> InlineKeyboardMarkup:
    buttons = []
    for key, product in PRODUCTS.items():
        is_selected = key in selected
        check = "✅" if is_selected else "⬜"
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
    bottom_row = [
        InlineKeyboardButton(text="❌ Отмена", callback_data="purchase_cancel"),
    ]
    if selected:
        bottom_row.append(
            InlineKeyboardButton(text="Далее ➡️", callback_data="purchase_next_duration"),
        )
    buttons.append(bottom_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def purchase_duration_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 месяц",    callback_data="pd:1m"),
            InlineKeyboardButton(text="3 месяца",   callback_data="pd:3m"),
        ],
        [
            InlineKeyboardButton(text="6 месяцев",  callback_data="pd:6m"),
            InlineKeyboardButton(text="12 месяцев", callback_data="pd:12m"),
        ],
        [
            InlineKeyboardButton(text="♾️ Безлимит", callback_data="pd:unlimited"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад",       callback_data="purchase_back_products"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="purchase_cancel"),
        ],
    ])


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
        InlineKeyboardButton(text="⬅️ Назад",       callback_data="purchase_next_duration"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="purchase_cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_link_kb(url: str, order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"pcheck:{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="purchase_cancel")],
    ])


def stars_payment_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pstars:{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="purchase_cancel")],
    ])
