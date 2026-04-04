import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone

from config import BOT_ADMIN_ID
from database import Database
from bot.formatting import format_server, clients_header
from bot.states import AddServerState, RenameState
from bot.keyboards.admin import (
    clients_kb, server_detail_kb, cancel_kb, add_period_kb, period_kb,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


async def _clear_confirm(state: FSMContext, bot: Bot, chat_id: int):
    data = await state.get_data()
    msg_id = data.get("confirm_msg_id")
    if msg_id:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    keys_to_keep = {k: v for k, v in data.items()
                    if k not in ("confirm_delete", "confirm_blacklist", "confirm_send", "confirm_msg_id")}
    await state.set_data(keys_to_keep)


# ── Список клиентов ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "clients")
async def cb_clients(call: CallbackQuery, state: FSMContext, db: Database):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    await call.message.edit_text(clients_header(len(servers)), reply_markup=clients_kb(servers))
    await call.answer()


# ── Отмена добавления ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_add")
async def cb_cancel_add(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    await call.message.edit_text(clients_header(len(servers)), reply_markup=clients_kb(servers))
    await call.answer()


# ── Статистика ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    total = len(servers)
    now = datetime.now(timezone.utc)
    active = expired = paused = blacklisted = 0
    for s in servers:
        if s.get("is_blacklisted"):
            blacklisted += 1
        elif not s["is_active"]:
            paused += 1
        elif s["expires_at"]:
            try:
                dt = datetime.fromisoformat(s["expires_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if now > dt:
                    expired += 1
                else:
                    active += 1
            except Exception:
                active += 1
        else:
            active += 1

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_panel", style="primary")]
    ])
    await call.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        f"Всего серверов: <b>{total}</b>\n"
        f"🟢 Активных: <b>{active}</b>\n"
        f"🟡 Истекших: <b>{expired}</b>\n"
        f"🔴 Приостановлено: <b>{paused}</b>\n"
        f"❌ Заблокировано: <b>{blacklisted}</b>",
        reply_markup=kb,
    )
    await call.answer()


# ── Карточка сервера ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("s:"))
async def cb_server_detail(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer()


# ── Переключение статуса из списка ────────────────────────────────────────────

@router.callback_query(F.data.startswith("tgl:"))
async def cb_toggle_from_list(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    if server.get("is_blacklisted"):
        await call.answer("⛔ Сервер заблокирован", show_alert=True)
        return
    new_active = 0 if server["is_active"] else 1
    await db.set_server_active(server_id, new_active)
    servers = await db.get_all_servers()
    await call.message.edit_text(clients_header(len(servers)), reply_markup=clients_kb(servers))
    await call.answer("▶️ Возобновлён" if new_active else "⏸ Приостановлен")


# ── Добавить сервер (admin) ────────────────────────────────────────────────────

@router.callback_query(F.data == "add")
async def cb_add_server(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AddServerState.waiting_name)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text("✏️ Введите название сервера:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AddServerState.waiting_name)
async def on_server_name(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    await state.update_data(name=message.text.strip())
    await state.set_state(AddServerState.waiting_period)
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(
                "🗓 Укажите длительность:",
                chat_id=chat_id,
                message_id=prompt_msg_id,
                reply_markup=add_period_kb(),
            )
            return
        except Exception:
            pass
    await message.answer("🗓 Укажите длительность:", reply_markup=add_period_kb())


@router.callback_query(F.data.startswith("ap:"))
async def cb_period_selected(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    period = call.data.split(":")[1]
    data = await state.get_data()
    name = data.get("name", "Без названия")
    await state.clear()
    server = await db.add_server(name, period)
    await call.message.edit_text(
        f"✅ Сервер добавлен\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await call.answer()


# ── Продлить ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ext:"))
async def cb_extend(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    current_state = await state.get_state()
    if current_state == AddServerState.waiting_period:
        return await call.answer()
    await _clear_confirm(state, call.bot, call.message.chat.id)

    from_list = False
    try:
        text = call.message.text or call.message.html_text or ""
        if "Список серверов" in text:
            from_list = True
    except Exception:
        pass

    back_cb = "clients" if from_list else f"s:{server_id}"
    await state.update_data(server_id=server_id, extend_back=back_cb)
    await call.message.edit_text(
        "🗓 Укажите длительность:",
        reply_markup=period_kb("ep", back_cb=back_cb),
    )
    await call.answer()


@router.callback_query(F.data.startswith("ep:"))
async def cb_extend_period(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    period = call.data.split(":")[1]
    data = await state.get_data()
    server_id = data.get("server_id")
    if not server_id:
        await call.answer("Ошибка", show_alert=True)
        return
    await state.clear()
    server = await db.extend_server(server_id, period)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer("✅ Тариф обновлён")


# ── Сбросить IP ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rip:"))
async def cb_reset_ip(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    server = await db.reset_server_ip(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer("✅ IP сброшен")


# ── Приостановить / Возобновить ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tog:"))
async def cb_toggle(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    new_active = 0 if server["is_active"] else 1
    server = await db.set_server_active(server_id, new_active)
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer("▶️ Возобновлён" if new_active else "⏸ Приостановлен")


# ── Заблокировать / Разблокировать ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("blk:"))
async def cb_blacklist(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    if server.get("is_blacklisted"):
        await _clear_confirm(state, call.bot, call.message.chat.id)
        server = await db.unblacklist_server(server_id)
        await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
        await call.answer("🔓 Сервер разблокирован")
        return

    data = await state.get_data()
    if data.get("confirm_blacklist") == server_id:
        pending_msg_id = data.get("confirm_msg_id")
        if pending_msg_id:
            try:
                await call.bot.delete_message(call.message.chat.id, pending_msg_id)
            except Exception:
                pass
        await state.update_data(confirm_blacklist=None, confirm_msg_id=None)
        server = await db.blacklist_server(server_id)
        await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
        await call.answer("🚫 Сервер заблокирован")
    else:
        await _clear_confirm(state, call.bot, call.message.chat.id)
        notify = await call.message.answer(
            "⚠️ Нажмите <b>Заблокировать</b> ещё раз для подтверждения"
        )
        await state.update_data(confirm_blacklist=server_id, confirm_msg_id=notify.message_id)

        async def _auto_clear():
            await asyncio.sleep(5)
            try:
                await notify.delete()
            except Exception:
                pass
            cur = await state.get_data()
            if cur.get("confirm_blacklist") == server_id:
                await state.update_data(confirm_blacklist=None, confirm_msg_id=None)

        asyncio.create_task(_auto_clear())
        await call.answer()


# ── Удалить ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del:"))
async def cb_delete(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    data = await state.get_data()

    if data.get("confirm_delete") == server_id:
        pending_msg_id = data.get("confirm_msg_id")
        if pending_msg_id:
            try:
                await call.bot.delete_message(call.message.chat.id, pending_msg_id)
            except Exception:
                pass
        await state.update_data(confirm_delete=None, confirm_msg_id=None)
        await db.delete_server(server_id)
        servers = await db.get_all_servers()
        await call.message.edit_text(clients_header(len(servers)), reply_markup=clients_kb(servers))
        await call.answer("🗑 Удалено")
    else:
        server = await db.get_server(server_id)
        if not server:
            await call.answer("Сервер не найден", show_alert=True)
            return
        await _clear_confirm(state, call.bot, call.message.chat.id)
        notify = await call.message.answer(
            "⚠️ Нажмите <b>Удалить</b> ещё раз для подтверждения"
        )
        await state.update_data(confirm_delete=server_id, confirm_msg_id=notify.message_id)

        async def _auto_clear():
            await asyncio.sleep(5)
            try:
                await notify.delete()
            except Exception:
                pass
            cur = await state.get_data()
            if cur.get("confirm_delete") == server_id:
                await state.update_data(confirm_delete=None, confirm_msg_id=None)

        asyncio.create_task(_auto_clear())
        await call.answer()


# ── Переименовать ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ren:"))
async def cb_rename(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    await state.set_state(RenameState.waiting_name)
    await state.update_data(server_id=server_id,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text("✏️ Введите новое название сервера:",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="❌ Отмена", callback_data=f"s:{server_id}", style="danger")]
                                 ]))
    await call.answer()


@router.message(RenameState.waiting_name)
async def on_rename(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    server_id = data.get("server_id")
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    await state.clear()
    server = await db.rename_server(server_id, message.text.strip())
    text = format_server(server) if server else "Сервер не найден."
    kb = server_detail_kb(server) if server else None
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)
