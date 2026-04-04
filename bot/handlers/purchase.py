import asyncio
import hashlib
import json
import logging
import uuid
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, Message, LabeledPrice,
    PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import BOT_ADMIN_ID, PUBLIC_URL
from database import Database, GATEWAY_TYPES
from bot.states import PurchaseState
from bot.keyboards.user import user_main_menu_kb
from bot.keyboards.purchase import (
    PRODUCTS, PURCHASE_DURATIONS, _format_price,
    product_selection_kb, purchase_duration_kb, payment_method_kb,
    payment_link_kb,
)

logger = logging.getLogger(__name__)
router = Router()

# Примерный курс: 1 Star ≈ 2 RUB (Telegram устанавливает курс)
STARS_RATE = 2


async def _auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 300):
    """Auto-delete a message after `delay` seconds."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _delete_notification(state: FSMContext, bot: Bot, chat_id: int):
    """Delete pending notification message stored in FSM state."""
    data = await state.get_data()
    note_id = data.get("_notification_id")
    if note_id:
        try:
            await bot.delete_message(chat_id, note_id)
        except Exception:
            pass
        await state.update_data(_notification_id=None)


_selection_quote = "\n\n".join(
    f"• <b>{p['name']}</b> — {p['description']}"
    for p in PRODUCTS.values()
)
_SELECTION_TEXT = (
    f"🛒 <b>Покупка ключа</b>\n\n"
    f"<blockquote>{_selection_quote}</blockquote>\n\n"
    f"Выберите продукты:"
)


def _products_block(selected: set[str]) -> str:
    """Header + blockquote with products and unlimited price. No trailing prompt."""
    product_lines = []
    total_unlimited = 0
    for key, p in PRODUCTS.items():
        if key not in selected:
            continue
        total_unlimited += p["price"]
        product_lines.append(f"{p['emoji']} {p['name']} — {_format_price(p['price_monthly'])} ₽/мес")
    product_lines.append(f"♾️ Безлимит: {_format_price(total_unlimited)} ₽ (единоразово)")
    quote = "\n\n".join(product_lines)
    return (
        f"🛒 <b>Покупка ключа</b>\n\n"
        f"Активируемые приложения:\n"
        f"<blockquote>{quote}</blockquote>"
    )


def _duration_text(selected: set[str]) -> str:
    return _products_block(selected) + "\n\nВыберите длительность:"


# ── Начало покупки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "purchase_start")
async def cb_purchase_start(call: CallbackQuery, state: FSMContext):
    await _delete_notification(state, call.bot, call.message.chat.id)
    await state.clear()
    await state.set_state(PurchaseState.selecting_products)
    await state.update_data(selected_products=[])
    await call.message.edit_text(_SELECTION_TEXT, reply_markup=product_selection_kb(set()))
    await call.answer()


@router.callback_query(F.data == "purchase_cancel")
async def cb_purchase_cancel(call: CallbackQuery, state: FSMContext, db: Database):
    await _delete_notification(state, call.bot, call.message.chat.id)
    await state.clear()
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    await call.message.edit_text(
        "🏠 <b>Главное меню</b>",
        reply_markup=user_main_menu_kb(support, community),
    )
    await call.answer()


@router.callback_query(F.data == "purchase_back_products")
async def cb_purchase_back_products(call: CallbackQuery, state: FSMContext):
    await _delete_notification(state, call.bot, call.message.chat.id)
    data = await state.get_data()
    selected = set(data.get("selected_products", []))
    await state.set_state(PurchaseState.selecting_products)
    await call.message.edit_text(_SELECTION_TEXT, reply_markup=product_selection_kb(selected))
    await call.answer()


# ── Выбор продуктов (toggle) ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("pt:"), PurchaseState.selecting_products)
async def cb_product_toggle(call: CallbackQuery, state: FSMContext):
    product_key = call.data.split(":")[1]
    if product_key not in PRODUCTS:
        return await call.answer("❌ Неизвестный продукт", show_alert=True)

    await _delete_notification(state, call.bot, call.message.chat.id)
    data = await state.get_data()
    selected = set(data.get("selected_products", []))

    if product_key in selected:
        selected.discard(product_key)
    else:
        selected.add(product_key)

    await state.update_data(selected_products=list(selected))
    await call.message.edit_text(_SELECTION_TEXT, reply_markup=product_selection_kb(selected))
    await call.answer()


# ── Переход к выбору длительности ──────────────────────────────────────────

@router.callback_query(F.data == "purchase_next_duration")
async def cb_purchase_next_duration(call: CallbackQuery, state: FSMContext):
    await _delete_notification(state, call.bot, call.message.chat.id)
    data = await state.get_data()
    selected = set(data.get("selected_products", []))
    if not selected:
        return await call.answer("Выберите хотя бы один продукт", show_alert=True)

    await state.set_state(PurchaseState.selecting_duration)
    await call.message.edit_text(_duration_text(selected), reply_markup=purchase_duration_kb())
    await call.answer()


# ── Выбор длительности ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pd:"), PurchaseState.selecting_duration)
async def cb_purchase_duration(call: CallbackQuery, state: FSMContext, db: Database):
    await _delete_notification(state, call.bot, call.message.chat.id)
    duration_key = call.data.split(":")[1]
    if duration_key not in PURCHASE_DURATIONS:
        return await call.answer("❌ Неизвестная длительность", show_alert=True)
    dur = PURCHASE_DURATIONS[duration_key]

    data = await state.get_data()
    selected = set(data.get("selected_products", []))

    gateways = await db.get_all_gateways()
    active_gateways = [gw for gw in gateways if gw["is_active"]]

    if not active_gateways:
        note = await call.message.answer(
            "⚠️ Нет доступных способов оплаты. Обратитесь к администратору."
        )
        await state.update_data(_notification_id=note.message_id)
        asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
        await call.answer()
        return

    await state.update_data(selected_duration=duration_key)
    await state.set_state(PurchaseState.selecting_payment)

    if duration_key == "unlimited":
        total = sum(PRODUCTS[k]["price"] for k in selected)
        dur_label = "Безлимит"
    else:
        total = sum(PRODUCTS[k]["price_monthly"] for k in selected) * dur["months"]
        dur_label = dur["label"]

    text = (
        f"{_products_block(selected)}\n\n"
        f"🗓 Длительность: <b>{dur_label}</b>\n"
        f"💳 К оплате: <b>{_format_price(total)} ₽</b>\n\n"
        f"Выберите способ оплаты:"
    )
    await call.message.edit_text(text, reply_markup=payment_method_kb(gateways))
    await call.answer()


# ── Выбор способа оплаты и создание заказа ─────────────────────────────────

@router.callback_query(F.data.startswith("pm:"), PurchaseState.selecting_payment)
async def cb_payment_method(call: CallbackQuery, state: FSMContext, db: Database):
    gateway_type = call.data.split(":")[1]
    data = await state.get_data()
    selected = set(data.get("selected_products", []))
    duration_key = data.get("selected_duration", "1m")

    if not selected:
        return await call.answer("Ошибка", show_alert=True)

    dur = PURCHASE_DURATIONS.get(duration_key)
    if not dur:
        return await call.answer("Ошибка", show_alert=True)

    # Вычисляем сумму
    if duration_key == "unlimited":
        total = sum(PRODUCTS[k]["price"] for k in selected)
    else:
        total = sum(PRODUCTS[k]["price_monthly"] for k in selected) * dur["months"]

    gw = await db.get_gateway(gateway_type)
    if not gw or not gw["is_active"]:
        return await call.answer("❌ Способ оплаты недоступен", show_alert=True)

    currency = await db.get_setting("payment_currency") or "RUB"

    # Создаём заказ
    order = await db.create_order(
        user_id=call.from_user.id,
        products=list(selected),
        duration=duration_key,
        amount=total,
        currency=currency,
        gateway=gateway_type,
    )
    order_id = order["id"]
    await state.set_state(PurchaseState.waiting_payment)
    await state.update_data(order_id=order_id)

    # Создаём платёж в зависимости от шлюза
    if gateway_type == "yoomoney":
        await _create_yoomoney_payment(call, db, gw, order_id, total, currency)
    elif gateway_type == "heleket":
        await _create_heleket_payment(call, db, gw, order_id, total, currency)
    elif gateway_type == "stars":
        await _create_stars_payment(call, state, db, order_id, total, selected, dur)
    else:
        await call.answer("❌ Шлюз не поддерживается", show_alert=True)


# ── YooMoney ───────────────────────────────────────────────────────────────

async def _create_yoomoney_payment(
    call: CallbackQuery, db: Database, gw: dict,
    order_id: str, amount: int, currency: str,
):
    settings = gw.get("settings", {})
    wallet_id = settings.get("wallet_id", "")
    if not wallet_id:
        return await call.answer("❌ ЮМани не настроен. Обратитесь к администратору.", show_alert=True)

    params = {
        "receiver": wallet_id,
        "quickpay-form": "shop",
        "targets": f"Лицензия #{order_id[:8]}",
        "paymentType": "AC",
        "sum": str(amount),
        "label": order_id,
    }
    payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?{urlencode(params)}"
    await db.update_order_payment_url(order_id, payment_url)

    text = (
        f"💳 <b>Оплата через ЮМани</b>\n\n"
        f"💰 Сумма: <b>{_format_price(amount)} {currency}</b>\n"
        f"🆔 Заказ: <code>{order_id[:8]}</code>\n\n"
        f"Нажмите кнопку ниже для оплаты:"
    )
    await call.message.edit_text(text, reply_markup=payment_link_kb(payment_url, order_id))
    await call.answer()


# ── Heleket ────────────────────────────────────────────────────────────────

async def _create_heleket_payment(
    call: CallbackQuery, db: Database, gw: dict,
    order_id: str, amount: int, currency: str,
):
    settings = gw.get("settings", {})
    merchant_id = settings.get("merchant_id", "")
    api_key = settings.get("api_key", "")
    if not merchant_id or not api_key:
        return await call.answer("❌ Heleket не настроен. Обратитесь к администратору.", show_alert=True)

    callback_url = f"{PUBLIC_URL.rstrip('/')}/api/v1/webhook/heleket" if PUBLIC_URL else ""

    payload = {
        "amount": str(amount),
        "currency": currency,
        "order_id": order_id,
        "url_callback": callback_url,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    sign_data = hashlib.md5(
        (json.dumps(payload, separators=(",", ":"), sort_keys=True).encode().hex() + api_key).encode()
    ).hexdigest()

    headers = {
        "merchant": merchant_id,
        "sign": sign_data,
        "Content-Type": "application/json",
    }

    try:
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            async with session.post(
                "https://api.heleket.com/v1/payment",
                data=payload_json,
                headers=headers,
            ) as resp:
                resp_data = await resp.json()
                if resp.status == 200 and resp_data.get("result"):
                    payment_url = resp_data["result"].get("url", "")
                    if payment_url:
                        await db.update_order_payment_url(order_id, payment_url)
                        text = (
                            f"🌐 <b>Оплата через Heleket</b>\n\n"
                            f"💰 Сумма: <b>{_format_price(amount)} {currency}</b>\n"
                            f"🆔 Заказ: <code>{order_id[:8]}</code>\n\n"
                            f"Нажмите кнопку ниже для оплаты:"
                        )
                        await call.message.edit_text(text, reply_markup=payment_link_kb(payment_url, order_id))
                        await call.answer()
                        return
                logger.error(f"[heleket] Create payment failed: {resp.status} {resp_data}")
                await call.answer("❌ Ошибка создания платежа. Попробуйте позже.", show_alert=True)
    except Exception as e:
        logger.error(f"[heleket] Error: {e}")
        await call.answer("❌ Ошибка подключения к Heleket", show_alert=True)


# ── Telegram Stars ─────────────────────────────────────────────────────────

async def _create_stars_payment(
    call: CallbackQuery, state: FSMContext, db: Database,
    order_id: str, amount_rub: int,
    selected: set[str], dur: dict,
):
    stars_amount = max(1, amount_rub // STARS_RATE)
    product_names = ", ".join(PRODUCTS[k]["name"] for k in selected)
    title = f"Лицензия: {product_names}"
    description = f"{dur['label']} — {product_names}"

    try:
        link = await call.bot.create_invoice_link(
            title=title[:32],
            description=description[:255],
            payload=order_id,
            currency="XTR",
            prices=[LabeledPrice(label=title[:32], amount=stars_amount)],
        )
        await db.update_order_payment_url(order_id, link)

        text = (
            f"⭐ <b>Оплата через Telegram Stars</b>\n\n"
            f"💰 Сумма: <b>{stars_amount} ⭐</b>\n"
            f"🆔 Заказ: <code>{order_id[:8]}</code>\n\n"
            f"Нажмите кнопку ниже для оплаты:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {stars_amount} Stars", url=link)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main", style="danger")],
        ])
        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()
    except Exception as e:
        logger.error(f"[stars] Create invoice error: {e}")
        await call.answer("❌ Ошибка создания счёта Stars", show_alert=True)


# ── Проверка оплаты ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pcheck:"))
async def cb_payment_check(call: CallbackQuery, state: FSMContext, db: Database):
    order_id = call.data.split(":")[1]
    order = await db.get_order(order_id)
    if not order:
        return await call.answer("Заказ не найден", show_alert=True)

    if order["status"] == "paid":
        # Уже оплачен — показать ключ
        await _deliver_key(call, state, db, order)
        return

    await call.answer("⏳ Оплата не получена. Попробуйте позже.", show_alert=True)


# ── Stars pre_checkout_query ───────────────────────────────────────────────

@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, db: Database):
    order_id = query.invoice_payload
    order = await db.get_pending_order(order_id)
    if order:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Заказ не найден или уже обработан")


# ── Stars successful_payment ──────────────────────────────────────────────

@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext, db: Database):
    payment = message.successful_payment
    order_id = payment.invoice_payload

    order = await db.complete_order(order_id, {
        "provider": "stars",
        "charge_id": payment.telegram_payment_charge_id,
        "total_amount": payment.total_amount,
        "currency": payment.currency,
    })

    if not order:
        return

    # Создаём сервер
    server = await db.add_server_for_user(
        user_id=order["user_id"],
        products=order["products"],
        duration=order["duration"],
    )

    key = server["license_key"]
    text = (
        "✅ <b>Оплата получена!</b>\n\n"
        f"🔑 Ваш лицензионный ключ:\n<code>{key}</code>\n\n"
        f"Используйте этот ключ для установки на вашем сервере."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary")],
    ])
    await message.answer(text, reply_markup=kb)

    # Уведомляем админа
    try:
        product_names = ", ".join(order["products"])
        admin_text = (
            f"🛒 <b>Новая покупка!</b>\n\n"
            f"👤 Пользователь: <code>{order['user_id']}</code>\n"
            f"📦 Продукты: {product_names}\n"
            f"💰 Сумма: {order['amount']} {order['currency']}\n"
            f"🔑 Ключ: <code>{key}</code>"
        )
        await message.bot.send_message(BOT_ADMIN_ID, admin_text)
    except Exception:
        pass


# ── Доставка ключа (общая) ────────────────────────────────────────────────

async def _deliver_key(call: CallbackQuery, state: FSMContext, db: Database, order: dict):
    """Показать ключ после оплаты."""
    await state.clear()

    # Ищем сервер привязанный к этому пользователю (по дате)
    servers = await db.find_servers_by_dev_id(order["user_id"])
    # Находим последний сервер
    key = ""
    if servers:
        key = servers[-1].get("license_key", "")

    if not key:
        # Создаём, если вдруг пропустили
        server = await db.add_server_for_user(
            user_id=order["user_id"],
            products=order["products"],
            duration=order["duration"],
        )
        key = server["license_key"]

    text = (
        "✅ <b>Оплата получена!</b>\n\n"
        f"🔑 Ваш лицензионный ключ:\n<code>{key}</code>\n\n"
        f"Используйте этот ключ для установки на вашем сервере."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()
