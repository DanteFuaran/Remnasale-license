import asyncio
from aiohttp import ClientSession, ClientTimeout
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from bot.banner import show
from bot.formatting import format_server
from bot.states import SendMessageState
from bot.keyboards.admin import compose_kb, server_detail_kb

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


def _compose_header(server: dict, text: str | None) -> str:
    preview = f"<blockquote>{text}</blockquote>" if text else "<blockquote><i>Текст не введён</i></blockquote>"
    return (
        f"✉️ Сообщение для <b>{server['name']}</b>\n\n"
        f"{preview}"
    )


@router.callback_query(F.data.startswith("msg:"))
async def cb_compose_menu(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await _notify(call, "Сервер не найден")
        return
    bot_token = server.get("bot_token", "") or ""
    dev_ids = server.get("dev_telegram_ids", "") or ""
    if not bot_token or not dev_ids:
        await _notify(call, "❌ Нет данных бота. Дождитесь проверки лицензии клиентом.")
        return
    await state.set_state(SendMessageState.composing)
    banner = await db.get_setting("banner_file_id")
    sent = await show(call, _compose_header(server, None),
                      reply_markup=compose_kb(server_id, has_text=False), banner=banner or "")
    await state.update_data(server_id=server_id, compose_text=None,
                            prompt_msg_id=sent.message_id,
                            prompt_chat_id=sent.chat.id)
    await call.answer()


@router.callback_query(F.data.startswith("cmt:"))
async def cb_compose_enter_text(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await state.set_state(SendMessageState.waiting_text)
    sent = await show(call, "📝 Введите текст сообщения:",
                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                          [InlineKeyboardButton(text="❌ Отмена", callback_data=f"msg:{server_id}", style="danger")]
                      ]))
    await state.update_data(prompt_msg_id=sent.message_id,
                            prompt_chat_id=sent.chat.id)
    await call.answer()


@router.message(SendMessageState.waiting_text)
async def on_compose_text(message: Message, state: FSMContext, db: Database):
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
    compose_text = message.text.strip() if message.text else ""
    await state.set_state(SendMessageState.composing)
    await state.update_data(compose_text=compose_text)
    server = await db.get_server(server_id)
    text = _compose_header(server, compose_text) if server else "Сервер не найден."
    kb = compose_kb(server_id, has_text=bool(compose_text)) if server else None
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            try:
                await message.bot.delete_message(chat_id, prompt_msg_id)
            except Exception:
                pass
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("cmp:"))
async def cb_compose_preview(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    server_id = int(call.data.split(":")[1])
    compose_text = data.get("compose_text") or ""
    if not compose_text:
        await _notify(call, "Нет текста для предпросмотра")
        return
    server = await db.get_server(server_id)
    if not server:
        await _notify(call, "Сервер не найден")
        return
    preview_text = (
        "📩 <b>Сообщение от администратора лицензий</b>\n\n"
        f"{compose_text}"
    )
    preview_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_preview", style="success")]
    ])
    await call.message.answer(f"👁 <b>Предпросмотр:</b>\n\n{preview_text}", reply_markup=preview_kb)
    await call.answer()


@router.callback_query(F.data == "dismiss_preview")
async def cb_dismiss_preview(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("cms:"))
async def cb_compose_send(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    server_id = int(call.data.split(":")[1])
    compose_text = data.get("compose_text") or ""
    if not compose_text:
        await _notify(call, "Нет текста для отправки")
        return

    if data.get("confirm_send") == server_id:
        pending_msg_id = data.get("confirm_msg_id")
        if pending_msg_id:
            try:
                await call.bot.delete_message(call.message.chat.id, pending_msg_id)
            except Exception:
                pass
        await state.update_data(confirm_send=None, confirm_msg_id=None)

        server = await db.get_server(server_id)
        if not server:
            await _notify(call, "Сервер не найден")
            return
        bot_token = server.get("bot_token", "") or ""
        dev_ids_raw = server.get("dev_telegram_ids", "") or ""
        dev_ids = [tid.strip() for tid in dev_ids_raw.split(",") if tid.strip()]

        msg_text = (
            "📩 <b>Сообщение от администратора лицензий</b>\n\n"
            f"{compose_text}"
        )
        sent_ok = 0
        for tid in dev_ids:
            try:
                async with ClientSession(timeout=ClientTimeout(total=10)) as session:
                    payload = {
                        "chat_id": int(tid),
                        "text": msg_text,
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": [[
                                {"text": "✅ Закрыть", "callback_data": "license_warning_close", "style": "success"}
                            ]]
                        },
                    }
                    async with session.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                    ) as resp:
                        if resp.status == 200:
                            sent_ok += 1
            except Exception:
                pass

        await state.clear()
        banner = await db.get_setting("banner_file_id")
        await show(call, f"✅ Сообщение отправлено ({sent_ok}/{len(dev_ids)})\n\n{format_server(server)}",
                   reply_markup=server_detail_kb(server), banner=banner or "")
        await call.answer("✅ Отправлено")
    else:
        await _clear_confirm(state, call.bot, call.message.chat.id)
        notify = await call.message.answer(
            "⚠️ Нажмите <b>Отправить</b> ещё раз для подтверждения"
        )
        await state.update_data(confirm_send=server_id, confirm_msg_id=notify.message_id)

        async def _auto_clear():
            await asyncio.sleep(5)
            try:
                await notify.delete()
            except Exception:
                pass
            cur = await state.get_data()
            if cur.get("confirm_send") == server_id:
                await state.update_data(confirm_send=None, confirm_msg_id=None)

        asyncio.create_task(_auto_clear())
        await call.answer()
