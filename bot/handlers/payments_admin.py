import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID, PUBLIC_URL
from database import Database, GATEWAY_TYPES
from bot.banner import show
from bot.states import GatewayFieldState
from bot.keyboards.settings import (
    payments_kb, gateway_detail_kb, gateway_placement_kb, gateway_currency_kb,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


async def _auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _notify(call: CallbackQuery, text: str, delay: int = 5):
    note = await call.message.answer(text)
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id, delay))
    await call.answer()


def _format_gateway_detail_text(gw: dict, meta: dict) -> str:
    label = meta.get("label", gw["type"])
    fields = meta.get("fields", {})
    settings = gw.get("settings") or {}
    copyable = meta.get("copyable", set())
    lines = [label]
    if fields:
        lines.append("")
        for field_key, field_label in fields.items():
            val = settings.get(field_key) or ""
            if val:
                val_display = f"<code>{val}</code>" if field_key in copyable else val
            else:
                val_display = "—"
            lines.append(f"• {field_label}: {val_display}")
        if not all(settings.get(f) for f in fields):
            lines.append("")
            lines.append("<i>Укажите все необходимые настройки</i>")
    return "\n".join(lines)


# ── Платёжные системы ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_payments")
async def cb_settings_payments(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gateways = await db.get_all_gateways()
    await show(call, "💳 <b>Платёжные системы</b>", reply_markup=payments_kb(gateways), db=db)
    await call.answer()


@router.callback_query(F.data.startswith("gw:"))
async def cb_gateway_detail(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.get_gateway(gtype)
    if not gw:
        await _notify(call, "Шлюз не найден")
        return
    meta = GATEWAY_TYPES.get(gtype, {})
    if not meta.get("fields"):
        await _notify(call, "ℹ️ Шлюз не требует настройки")
        return
    await show(call, _format_gateway_detail_text(gw, meta),
               reply_markup=gateway_detail_kb(gw, PUBLIC_URL), db=db)
    await call.answer()
async def cb_gateway_test(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.get_gateway(gtype)
    if not gw:
        await _notify(call, "Шлюз не найден")
        return
    meta = GATEWAY_TYPES.get(gtype, {})
    fields = meta.get("fields", {})
    settings = gw.get("settings", {})
    if fields and not all(settings.get(f) for f in fields):
        await _notify(call, "❌ Шлюз не настроен")
        return
    if not gw["is_active"]:
        await _notify(call, "❌ Шлюз выключен")
        return
    label = meta.get("label", gtype)
    await _notify(call, f"🐞 Тестовый платёж {label}: в разработке")


@router.callback_query(F.data.startswith("gwt:"))
async def cb_gateway_toggle(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.toggle_gateway(gtype)
    if not gw:
        await _notify(call, "Шлюз не найден")
        return
    status = "🟢 Включён" if gw["is_active"] else "🔴 Выключен"
    gateways = await db.get_all_gateways()
    await show(call, "💳 <b>Платёжные системы</b>", reply_markup=payments_kb(gateways), db=db)
    await call.answer(status)


@router.callback_query(F.data.startswith("gwf:"))
async def cb_gateway_field(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    parts = call.data.split(":")
    gtype, field = parts[1], parts[2]
    meta = GATEWAY_TYPES.get(gtype, {})
    field_label = meta.get("fields", {}).get(field, field)
    await state.set_state(GatewayFieldState.waiting_value)
    await state.update_data(gw_type=gtype, gw_field=field,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    gw = await db.get_gateway(gtype)
    current = (gw.get("settings", {}).get(field, "") if gw else "") or "Не указан"
    await show(call, f"✏️ <b>{field_label}</b>\n\n"
               f"<blockquote>{current}</blockquote>\n\n"
               f"ℹ️ <i>Введите новое значение:</i>",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"gwfc:{gtype}:{field}", style="danger")],
                   [
                       InlineKeyboardButton(text="❌ Отмена", callback_data=f"gw:{gtype}", style="danger"),
                       InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary"),
                   ],
               ]), db=db)
    await call.answer()


@router.callback_query(F.data.startswith("gwfc:"))
async def cb_gateway_field_clear(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    parts = call.data.split(":")
    gtype, field = parts[1], parts[2]
    await db.clear_gateway_field(gtype, field)
    await state.clear()
    gw = await db.get_gateway(gtype)
    meta = GATEWAY_TYPES.get(gtype, {})
    await show(call, _format_gateway_detail_text(gw, meta),
               reply_markup=gateway_detail_kb(gw, PUBLIC_URL), db=db)
    await call.answer("🗑 Очищено")


@router.message(GatewayFieldState.waiting_value)
async def on_gateway_field_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    gtype = data.get("gw_type")
    field = data.get("gw_field")
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    val = message.text.strip() if message.text else ""
    await db.update_gateway_field(gtype, field, val)
    await state.clear()
    gw = await db.get_gateway(gtype)
    meta = GATEWAY_TYPES.get(gtype, {})
    text = f"✅ Сохранено\n\n{_format_gateway_detail_text(gw, meta)}"
    kb = gateway_detail_kb(gw, PUBLIC_URL)
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


# ── Позиционирование шлюзов ───────────────────────────────────────────────────

@router.callback_query(F.data == "gw_placement")
async def cb_gw_placement(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gateways = await db.get_all_gateways()
    await show(call, "🔢 <b>Позиционирование платёжных систем</b>\n\n"
               "Измените порядок отображения шлюзов:",
               reply_markup=gateway_placement_kb(gateways), db=db)
    await call.answer()


@router.callback_query(F.data == "gwup_noop")
async def cb_gw_up_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("gwup:"))
async def cb_gw_up(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gateways = await db.get_all_gateways()
    types = [gw["type"] for gw in gateways]
    idx = types.index(gtype) if gtype in types else -1
    if idx > 0:
        types[idx], types[idx - 1] = types[idx - 1], types[idx]
        await db.set_gateway_order(types)
        gateways = await db.get_all_gateways()
    await call.message.edit_reply_markup(reply_markup=gateway_placement_kb(gateways))
    await call.answer()


@router.callback_query(F.data.startswith("gwdn:"))
async def cb_gw_down(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gateways = await db.get_all_gateways()
    types = [gw["type"] for gw in gateways]
    idx = types.index(gtype) if gtype in types else -1
    if 0 <= idx < len(types) - 1:
        types[idx], types[idx + 1] = types[idx + 1], types[idx]
        await db.set_gateway_order(types)
        gateways = await db.get_all_gateways()
    await call.message.edit_reply_markup(reply_markup=gateway_placement_kb(gateways))
    await call.answer()


# ── Валюта по умолчанию ────────────────────────────────────────────────────────

@router.callback_query(F.data == "gw_currency")
async def cb_gw_currency(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = await db.get_setting("payment_currency") or "RUB"
    await show(call, "💸 <b>Валюта по умолчанию</b>\n\nВыберите валюту:",
               reply_markup=gateway_currency_kb(current), db=db)
    await call.answer()


@router.callback_query(F.data.startswith("gwcur:"))
async def cb_gw_currency_set(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    cur = call.data.split(":")[1]
    await db.set_setting("payment_currency", cur)
    await call.message.edit_reply_markup(reply_markup=gateway_currency_kb(cur))
    await call.answer(f"✅ {cur}")
