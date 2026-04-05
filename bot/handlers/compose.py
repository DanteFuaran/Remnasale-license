import asyncio
from aiohttp import ClientSession, ClientTimeout
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from aiogram.types import InputMediaPhoto
from bot.banner import show
from bot.formatting import format_server, clients_header
from bot.states import SendMessageState, BroadcastState, QuickReplyState
from bot.keyboards.admin import compose_kb, server_detail_kb, clients_kb

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


def _broadcast_header(text: str | None) -> str:
    preview = f"<blockquote>{text}</blockquote>" if text else "<blockquote><i>Текст не введён</i></blockquote>"
    return f"📢 <b>Рассылка всем клиентам</b>\n\n{preview}"


def _broadcast_kb(has_text: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Ввести текст", callback_data="bct")],
    ]
    if has_text:
        buttons.append([
            InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bcp"),
            InlineKeyboardButton(text="📤 Отправить всем", callback_data="bcs", style="success"),
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="clients", style="primary"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "broadcast")
async def cb_broadcast_menu(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.set_state(BroadcastState.composing)
    await state.update_data(broadcast_text=None)
    sent = await show(call, _broadcast_header(None), reply_markup=_broadcast_kb(False), db=db)
    await state.update_data(prompt_msg_id=sent.message_id, prompt_chat_id=sent.chat.id)
    await call.answer()


@router.callback_query(F.data == "bct")
async def cb_broadcast_enter_text(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(BroadcastState.waiting_text)
    sent = await show(call, "📝 Введите текст рассылки:",
                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                          [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast", style="danger")]
                      ]), db=db)
    await state.update_data(prompt_msg_id=sent.message_id, prompt_chat_id=sent.chat.id)
    await call.answer()


@router.message(BroadcastState.waiting_text)
async def on_broadcast_text(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    broadcast_text = message.text.strip() if message.text else ""
    await state.set_state(BroadcastState.composing)
    await state.update_data(broadcast_text=broadcast_text)
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id, prompt_msg_id)
        except Exception:
            pass
    sent = await show(message, _broadcast_header(broadcast_text),
                      reply_markup=_broadcast_kb(bool(broadcast_text)), db=db)
    await state.update_data(prompt_msg_id=sent.message_id, prompt_chat_id=sent.chat.id)


@router.callback_query(F.data == "bcp")
async def cb_broadcast_preview(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text") or ""
    if not broadcast_text:
        await _notify(call, "Нет текста для предпросмотра")
        return
    preview_text = "📩 <b>Сообщение от администратора лицензий</b>\n\n" + broadcast_text
    preview_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_broadcast_preview", style="success")]
    ])
    await call.message.answer(f"👁 <b>Предпросмотр:</b>\n\n{preview_text}", reply_markup=preview_kb)
    await call.answer()


@router.callback_query(F.data == "dismiss_broadcast_preview")
async def cb_dismiss_broadcast_preview(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "bcs")
async def cb_broadcast_send(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text") or ""
    if not broadcast_text:
        await _notify(call, "Нет текста для отправки")
        return

    if data.get("confirm_broadcast"):
        pending_msg_id = data.get("confirm_msg_id")
        if pending_msg_id:
            try:
                await call.bot.delete_message(call.message.chat.id, pending_msg_id)
            except Exception:
                pass
        await state.update_data(confirm_broadcast=None, confirm_msg_id=None)

        servers = await db.get_all_servers()
        active_servers = [s for s in servers if s.get("bot_token") and s.get("dev_telegram_ids")]

        msg_text = "📩 <b>Сообщение от администратора лицензий</b>\n\n" + broadcast_text
        banner_file_id = await db.get_setting("banner_file_id") or ""
        banner_bytes = b""
        if banner_file_id:
            try:
                buf = await call.bot.download(banner_file_id)
                if buf:
                    banner_bytes = buf.getvalue()
            except Exception:
                banner_bytes = b""
        reply_markup_json = (
            '{"inline_keyboard":['
            '[{"text":"✉️ Написать администратору","callback_data":"license_reply_admin"}],'
            '[{"text":"✅ Закрыть","callback_data":"license_warning_close","style":"success"}]'
            ']}'
        )
        sent_ok = 0
        total = 0
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            for server in active_servers:
                bot_token = server["bot_token"]
                dev_ids = [tid.strip() for tid in server["dev_telegram_ids"].split(",") if tid.strip()]
                for tid in dev_ids:
                    total += 1
                    try:
                        if banner_bytes:
                            from aiohttp import FormData
                            form = FormData()
                            form.add_field("chat_id", str(tid))
                            form.add_field("caption", msg_text)
                            form.add_field("parse_mode", "HTML")
                            form.add_field("reply_markup", reply_markup_json)
                            form.add_field("photo", banner_bytes,
                                           filename="banner.jpg", content_type="image/jpeg")
                            async with session.post(
                                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                                data=form,
                            ) as resp:
                                if resp.status == 200:
                                    sent_ok += 1
                                    continue
                        payload = {
                            "chat_id": int(tid),
                            "text": msg_text,
                            "parse_mode": "HTML",
                            "reply_markup": {"inline_keyboard": [
                                [{"text": "✉️ Написать администратору", "callback_data": "license_reply_admin"}],
                                [{"text": "✅ Закрыть", "callback_data": "license_warning_close", "style": "success"}],
                            ]},
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
        servers_all = await db.get_all_servers()
        await show(call, f"✅ Рассылка завершена: {sent_ok}/{total}\n\n{clients_header(len(servers_all))}",
                   reply_markup=clients_kb(servers_all), db=db)
        await call.answer("✅ Отправлено")
    else:
        await _clear_confirm(state, call.bot, call.message.chat.id)
        notify = await call.message.answer(
            f"⚠️ Нажмите <b>Отправить всем</b> ещё раз для подтверждения"
        )
        await state.update_data(confirm_broadcast=True, confirm_msg_id=notify.message_id)

        async def _auto_clear():
            await asyncio.sleep(5)
            try:
                await notify.delete()
            except Exception:
                pass
            cur = await state.get_data()
            if cur.get("confirm_broadcast"):
                await state.update_data(confirm_broadcast=None, confirm_msg_id=None)

        asyncio.create_task(_auto_clear())
        await call.answer()


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
    sent = await show(call, _compose_header(server, None),
                      reply_markup=compose_kb(server_id, has_text=False), db=db)
    await state.update_data(server_id=server_id, compose_text=None,
                            prompt_msg_id=sent.message_id,
                            prompt_chat_id=sent.chat.id)
    await call.answer()


@router.callback_query(F.data.startswith("cmt:"))
async def cb_compose_enter_text(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await state.set_state(SendMessageState.waiting_text)
    sent = await show(call, "📝 Введите текст сообщения:",
                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                          [InlineKeyboardButton(text="❌ Отмена", callback_data=f"msg:{server_id}", style="danger")]
                      ]), db=db)
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
    # Удаляем старый промпт (фото-сообщение с баннером нельзя отредактировать через edit_message_text)
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id, prompt_msg_id)
        except Exception:
            pass
    await show(message, text, reply_markup=kb, db=db)


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


@router.callback_query(F.data == "dismiss_client_msg")
async def cb_dismiss_client_msg(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


# ── Быстрый ответ на сообщение клиента ────────────────────────────────────────

@router.callback_query(F.data.startswith("qreply:"))
async def cb_quick_reply(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await _notify(call, "Сервер не найден")
        return
    await state.set_state(QuickReplyState.waiting_text)
    await state.update_data(server_id=server_id,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="qreply_cancel", style="danger")]
    ])
    msg = call.message
    if msg.photo:
        try:
            media = InputMediaPhoto(media=msg.photo[-1].file_id,
                                    caption="📝 Введите ответ клиенту:",
                                    parse_mode="HTML")
            await msg.edit_media(media=media, reply_markup=kb)
        except Exception:
            pass
    else:
        try:
            await msg.edit_text("📝 Введите ответ клиенту:", reply_markup=kb)
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data == "qreply_cancel")
async def cb_quick_reply_cancel(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


@router.message(QuickReplyState.waiting_text)
async def on_quick_reply_text(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    server_id = data.get("server_id")
    prompt_msg_id = data.get("prompt_msg_id")
    prompt_chat_id = data.get("prompt_chat_id") or message.chat.id
    compose_text = message.text.strip() if message.text else ""
    await state.clear()

    if prompt_msg_id:
        try:
            await message.bot.delete_message(prompt_chat_id, prompt_msg_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass

    if not compose_text:
        return

    server = await db.get_server(server_id)
    if not server:
        note = await message.answer("❌ Сервер не найден")
        asyncio.create_task(_auto_delete(message.bot, message.chat.id, note.message_id))
        return

    bot_token = server.get("bot_token", "") or ""
    dev_ids_raw = server.get("dev_telegram_ids", "") or ""
    dev_ids = [tid.strip() for tid in dev_ids_raw.split(",") if tid.strip()]
    if not bot_token or not dev_ids:
        note = await message.answer("❌ Нет данных бота клиента")
        asyncio.create_task(_auto_delete(message.bot, message.chat.id, note.message_id))
        return

    msg_text = (
        "📩 <b>Сообщение от администратора лицензий</b>\n\n"
        f"{compose_text}"
    )
    banner_file_id = await db.get_setting("banner_file_id") or ""
    banner_bytes = b""
    if banner_file_id:
        try:
            buf = await message.bot.download(banner_file_id)
            if buf:
                banner_bytes = buf.getvalue()
        except Exception:
            banner_bytes = b""
    reply_markup_json = (
        '{"inline_keyboard":['
        '[{"text":"✉️ Написать администратору","callback_data":"license_reply_admin"}],'
        '[{"text":"✅ Закрыть","callback_data":"license_warning_close","style":"success"}]'
        ']}'
    )
    sent_ok = 0
    async with ClientSession(timeout=ClientTimeout(total=15)) as session:
        for tid in dev_ids:
            try:
                if banner_bytes:
                    from aiohttp import FormData
                    form = FormData()
                    form.add_field("chat_id", str(tid))
                    form.add_field("caption", msg_text)
                    form.add_field("parse_mode", "HTML")
                    form.add_field("reply_markup", reply_markup_json)
                    form.add_field("photo", banner_bytes,
                                   filename="banner.jpg", content_type="image/jpeg")
                    async with session.post(
                        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                        data=form,
                    ) as resp:
                        if resp.status == 200:
                            sent_ok += 1
                            continue
                payload = {
                    "chat_id": int(tid),
                    "text": msg_text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": [
                        [{"text": "✉️ Написать администратору", "callback_data": "license_reply_admin"}],
                        [{"text": "✅ Закрыть", "callback_data": "license_warning_close", "style": "success"}],
                    ]},
                }
                async with session.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        sent_ok += 1
            except Exception:
                pass

    note = await message.answer(f"✅ Ответ отправлен ({sent_ok}/{len(dev_ids)})")
    asyncio.create_task(_auto_delete(message.bot, message.chat.id, note.message_id))


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
        # Скачиваем байты баннера через наш бот — file_id другому боту недоступен
        banner_file_id = await db.get_setting("banner_file_id") or ""
        banner_bytes = b""
        if banner_file_id:
            try:
                buf = await call.bot.download(banner_file_id)
                if buf:
                    banner_bytes = buf.getvalue()
            except Exception:
                banner_bytes = b""
        reply_markup_json = (
            '{"inline_keyboard":['
            '[{"text":"✉️ Написать администратору","callback_data":"license_reply_admin"}],'
            '[{"text":"✅ Закрыть","callback_data":"license_warning_close","style":"success"}]'
            ']}'
        )
        sent_ok = 0
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            for tid in dev_ids:
                try:
                    if banner_bytes:
                        from aiohttp import FormData
                        form = FormData()
                        form.add_field("chat_id", str(tid))
                        form.add_field("caption", msg_text)
                        form.add_field("parse_mode", "HTML")
                        form.add_field("reply_markup", reply_markup_json)
                        form.add_field("photo", banner_bytes,
                                       filename="banner.jpg", content_type="image/jpeg")
                        async with session.post(
                            f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                            data=form,
                        ) as resp:
                            if resp.status == 200:
                                sent_ok += 1
                                continue
                    # Fallback / no banner
                    payload = {
                        "chat_id": int(tid),
                        "text": msg_text,
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": [
                            [{"text": "✉️ Написать администратору", "callback_data": "license_reply_admin"}],
                            [{"text": "✅ Закрыть", "callback_data": "license_warning_close", "style": "success"}],
                        ]},
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
        await show(call, f"✅ Сообщение отправлено ({sent_ok}/{len(dev_ids)})\n\n{format_server(server)}",
                   reply_markup=server_detail_kb(server), db=db)
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
