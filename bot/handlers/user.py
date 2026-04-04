from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import BOT_ADMIN_ID
from database import Database
from bot.formatting import format_user_server
from bot.keyboards.user import (
    user_servers_kb, user_server_kb,
    user_view_servers_kb, user_view_server_kb,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


# ── Мои серверы ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_servers")
async def cb_my_servers(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    user_id = call.from_user.id
    servers = await db.find_servers_by_dev_id(user_id)
    if not servers:
        await call.message.edit_text(
            "🖥 <b>Мои серверы</b>\n\nУ вас пока нет серверов.",
            reply_markup=user_servers_kb([]),
        )
        return await call.answer()
    if len(servers) == 1:
        server = servers[0]
        support = await db.get_setting("support_url")
        community = await db.get_setting("community_url")
        await call.message.edit_text(
            format_user_server(server),
            reply_markup=user_server_kb(server, support, community),
        )
        return await call.answer()
    await call.message.edit_text(
        "🖥 <b>Мои серверы:</b>",
        reply_markup=user_servers_kb(servers),
    )
    await call.answer()


# ── Просмотр сервера пользователем ──────────────────────────────────────────

@router.callback_query(F.data.startswith("us:"))
async def cb_user_server(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    uid = str(call.from_user.id)
    is_dev = uid in [t.strip() for t in dev_ids]
    if not is_dev and not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    # Admin in role-switch mode
    if _is_admin(call.from_user.id) and not is_dev:
        from bot.keyboards.user import user_view_server_kb
        await call.message.edit_text(
            format_user_server(server),
            reply_markup=user_view_server_kb(server, support, community),
        )
    else:
        await call.message.edit_text(
            format_user_server(server),
            reply_markup=user_server_kb(server, support, community),
        )
    await call.answer()


# ── Продлить (пользователь) ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("uext:"))
async def cb_user_extend(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    if str(call.from_user.id) not in [t.strip() for t in dev_ids]:
        return await call.answer("⛔")
    await call.answer("💳 Платежные системы пока не настроены. Обратитесь к администратору.", show_alert=True)
