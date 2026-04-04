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


async def _clear_chat(bot: Bot, chat_id: int, up_to_msg_id: int):
    """Удаляет предыдущие сообщения в фоне."""
    for msg_id in range(up_to_msg_id, max(0, up_to_msg_id - 100), -1):
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass


async def _clear_chat_bg(bot: Bot, chat_id: int, up_to_msg_id: int):
    """Запускает очистку чата в фоне через asyncio.create_task."""
    asyncio.create_task(_clear_chat(bot, chat_id, up_to_msg_id))


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    banner = await db.get_setting("banner_file_id")
    is_admin = _is_admin(message.from_user.id)
    kb = user_main_menu_kb(support, community, is_admin=is_admin)
    text = "🏠 <b>Главное меню</b>"
    if banner:
        try:
            await message.answer_photo(photo=banner)
        except Exception:
            pass
    menu_msg = await message.answer(text, reply_markup=kb)
    # Удаляем всё до нового сообщения (саму /start включительно)
    await _clear_chat_bg(message.bot, message.chat.id, menu_msg.message_id - 1)


@router.callback_query(F.data == "main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    data = await state.get_data()
    note_id = data.get("_notification_id")
    if note_id:
        try:
            await call.bot.delete_message(call.message.chat.id, note_id)
        except Exception:
            pass
    await state.clear()
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    is_admin = _is_admin(call.from_user.id)
    await call.message.edit_text(
        "🏠 <b>Главное меню</b>",
        reply_markup=user_main_menu_kb(support, community, is_admin=is_admin),
    )
    await call.answer()


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    await call.message.edit_text("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(F.data == "role_switch")
async def cb_role_switch(call: CallbackQuery, state: FSMContext, db: Database):
    """Alias — сейчас просто перенаправляет на cb_main_menu (main)."""
    await call.answer()
    await cb_main_menu(call, state, db)
