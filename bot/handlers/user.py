import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import BOT_ADMIN_ID
from database import Database
from bot.banner import show
from bot.formatting import format_user_server
from bot.keyboards.user import (
    user_servers_kb, user_server_kb,
    user_view_servers_kb, user_view_server_kb,
)

router = Router()


async def _auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _delete_notification(state: FSMContext, bot: Bot, chat_id: int):
    data = await state.get_data()
    note_id = data.get("_notification_id")
    if note_id:
        try:
            await bot.delete_message(chat_id, note_id)
        except Exception:
            pass
        await state.update_data(_notification_id=None)


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


# ── Мои серверы ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_servers")
async def cb_my_servers(call: CallbackQuery, state: FSMContext, db: Database):
    await _delete_notification(state, call.bot, call.message.chat.id)
    await state.clear()
    user_id = call.from_user.id
    servers = await db.find_servers_by_owner(user_id)
    if not servers:
        await show(call, "🖥 <b>Мои серверы</b>\n\nУ вас пока нет серверов.",
                   reply_markup=user_servers_kb([]), db=db)
        return await call.answer()
    if len(servers) == 1:
        server = servers[0]
        support = await db.get_setting("support_url")
        community = await db.get_setting("community_url")
        await show(call, format_user_server(server),
                   reply_markup=user_server_kb(server, support, community, back_callback="main"), db=db)
        return await call.answer()
    await show(call, "🖥 <b>Мои серверы:</b>",
               reply_markup=user_servers_kb(servers), db=db)
    await call.answer()


# ── Просмотр сервера пользователем ──────────────────────────────────────────

@router.callback_query(F.data.startswith("us:"))
async def cb_user_server(call: CallbackQuery, state: FSMContext, db: Database):
    await _delete_notification(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        note = await call.message.answer("Сервер не найден")
        asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
        await call.answer()
        return
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    uid = str(call.from_user.id)
    owner = (server.get("owner_telegram_id", "") or "").strip()
    is_dev = uid in [t.strip() for t in dev_ids]
    is_owner = uid == owner
    if not is_dev and not is_owner and not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    # Admin in role-switch mode
    if _is_admin(call.from_user.id) and not is_dev and not is_owner:
        from bot.keyboards.user import user_view_server_kb
        await show(call, format_user_server(server),
                   reply_markup=user_view_server_kb(server, support, community), db=db)
    else:
        await show(call, format_user_server(server),
                   reply_markup=user_server_kb(server, support, community), db=db)
    await call.answer()


# ── Продлить (пользователь) ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("uextl:"))
async def cb_user_extend_from_list(call: CallbackQuery, state: FSMContext, db: Database):
    """Продлить из списка серверов — Назад вернёт в список серверов."""
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        note = await call.message.answer("Сервер не найден")
        asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
        await call.answer()
        return
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    owner = (server.get("owner_telegram_id", "") or "").strip()
    uid = str(call.from_user.id)
    if uid not in [t.strip() for t in dev_ids] and uid != owner and not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    note = await call.message.answer(
        "⚠️ Нет доступных способов оплаты. Обратитесь к администратору."
    )
    await state.update_data(_notification_id=note.message_id)
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
    await call.answer()


@router.callback_query(F.data.startswith("uext:"))
async def cb_user_extend(call: CallbackQuery, state: FSMContext, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        note = await call.message.answer("Сервер не найден")
        asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
        await call.answer()
        return
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    owner = (server.get("owner_telegram_id", "") or "").strip()
    uid = str(call.from_user.id)
    if uid not in [t.strip() for t in dev_ids] and uid != owner:
        return await call.answer("⛔")
    await _delete_notification(state, call.bot, call.message.chat.id)
    note = await call.message.answer(
        "⚠️ Нет доступных способов оплаты. Обратитесь к администратору."
    )
    await state.update_data(_notification_id=note.message_id)
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
    await call.answer()
