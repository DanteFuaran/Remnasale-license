import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import BOT_ADMIN_ID
from database import Database
from bot.formatting import format_user_server
from bot.keyboards.admin import main_menu_kb
from bot.keyboards.user import (
    user_main_menu_kb,
    user_view_servers_kb, user_view_server_kb, user_view_empty_kb,
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


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    if _is_admin(message.from_user.id):
        return await message.answer("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    await message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=user_main_menu_kb(support, community),
    )


@router.callback_query(F.data == "main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    if _is_admin(call.from_user.id):
        await call.message.edit_text("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
        return await call.answer()
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    await call.message.edit_text(
        "🏠 <b>Главное меню</b>",
        reply_markup=user_main_menu_kb(support, community),
    )
    await call.answer()


@router.callback_query(F.data == "role_switch")
async def cb_role_switch(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    servers = await db.find_servers_by_dev_id(call.from_user.id)
    if not servers:
        await call.message.edit_text(
            "👤 <b>Режим пользователя</b>\n\nУ вас нет привязанных серверов.",
            reply_markup=user_view_empty_kb(),
        )
    elif len(servers) == 1:
        server = servers[0]
        support = await db.get_setting("support_url")
        community = await db.get_setting("community_url")
        await call.message.edit_text(
            format_user_server(server),
            reply_markup=user_view_server_kb(server, support, community),
        )
    else:
        await call.message.edit_text(
            "🖥️ <b>Ваши серверы:</b>",
            reply_markup=user_view_servers_kb(servers),
        )
    await call.answer()
