import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from bot.banner import show
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
    """Удаляет все сообщения бота, начиная с up_to_msg_id и уходя далеко назад.

    Telegram позволяет боту удалять собственные сообщения в личном чате без
    ограничений по давности. Чужие сообщения (команды пользователя) просто
    упадут с ошибкой и будут проигнорированы.
    """
    LOOKBACK = 5000          # максимум сообщений назад
    BATCH    = 50            # сколько удаляем за один round
    end_id   = max(1, up_to_msg_id - LOOKBACK)
    current  = up_to_msg_id
    while current >= end_id:
        batch_start = current
        batch_end   = max(end_id, current - BATCH + 1)
        tasks = [
            bot.delete_message(chat_id, mid)
            for mid in range(batch_start, batch_end - 1, -1)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        current = batch_end - 1
        if current >= end_id:
            await asyncio.sleep(0.05)  # мягкая пауза, чтобы не упереться в rate-limit


async def _clear_chat_bg(bot: Bot, chat_id: int, up_to_msg_id: int):
    """Запускает очистку чата в фоне через asyncio.create_task."""
    asyncio.create_task(_clear_chat(bot, chat_id, up_to_msg_id))


async def _auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    user = message.from_user

    # Регистрация пользователя
    _, is_new = await db.register_user(
        telegram_id=user.id,
        full_name=user.full_name or "",
        username=user.username or "",
    )

    # Уведомление админа о новом пользователе
    if is_new and not _is_admin(user.id):
        username_display = f"@{user.username}" if user.username else "—"
        total_users = await db.get_users_count()
        admin_text = (
            f"👤 <b>Новый пользователь!</b>\n\n"
            f"<blockquote>👤 Имя: {user.full_name or '—'}\n"
            f"📱 Username: {username_display}\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"📊 Всего пользователей: {total_users}</blockquote>"
        )
        try:
            note = await message.bot.send_message(
                BOT_ADMIN_ID, admin_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Закрыть", callback_data="close_admin_note", style="success")],
                ]),
            )
        except Exception:
            pass

    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    is_admin = _is_admin(message.from_user.id)
    kb = user_main_menu_kb(support, community, is_admin=is_admin)
    text = "🏠 <b>Главное меню</b>"
    menu_msg = await show(message, text, reply_markup=kb, db=db)
    # Удаляем всё до нового сообщения (саму /start включительно)
    await _clear_chat_bg(message.bot, message.chat.id, menu_msg.message_id - 1)


@router.callback_query(F.data == "close_admin_note")
async def cb_close_admin_note(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


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
    key_note_id = data.get("_key_note_id")
    if key_note_id:
        try:
            await call.bot.delete_message(call.message.chat.id, key_note_id)
        except Exception:
            pass
    await state.clear()
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    is_admin = _is_admin(call.from_user.id)
    await show(call, "🏠 <b>Главное меню</b>",
               reply_markup=user_main_menu_kb(support, community, is_admin=is_admin),
               db=db)
    await call.answer()


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    await show(call, "🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb(), db=db)
    await call.answer()


# ── Показать ключ (общий для admin и user) ─────────────────────────────────

@router.callback_query(F.data.startswith("showkey:"))
async def cb_show_key(call: CallbackQuery, state: FSMContext, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer()
        return

    key = server.get("license_key", "—")
    note = await call.message.answer(f"🔑 <code>{key}</code>")
    await state.update_data(_key_note_id=note.message_id)
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id, 15))
    await call.answer()


@router.callback_query(F.data == "role_switch")
async def cb_role_switch(call: CallbackQuery, state: FSMContext, db: Database):
    """Alias — сейчас просто перенаправляет на cb_main_menu (main)."""
    await call.answer()
    await cb_main_menu(call, state, db)
