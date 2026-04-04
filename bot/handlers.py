import asyncio
import io
import json
from aiohttp import ClientSession, ClientTimeout
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile, Document,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from datetime import datetime, timezone, timedelta

from config import BOT_ADMIN_ID
from database import Database
from bot.keyboards import (
    main_menu_kb, clients_kb, period_kb, add_period_kb, cancel_kb,
    server_detail_kb, backup_kb, settings_kb,
    server_status, PERIOD_LABELS,
)

router = Router()

MSK_OFFSET = timedelta(hours=3)


class AddServerState(StatesGroup):
    waiting_name = State()
    waiting_period = State()


class RenameState(StatesGroup):
    waiting_name = State()


class SettingsIntervalState(StatesGroup):
    waiting_interval = State()


class SettingsOfflineGraceState(StatesGroup):
    waiting_days = State()


class SendMessageState(StatesGroup):
    waiting_text = State()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


def _pluralize_servers(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return f"{n} серверов"
    r = n % 10
    if r == 1:
        return f"{n} сервер"
    elif 2 <= r <= 4:
        return f"{n} сервера"
    return f"{n} серверов"


def format_server(server: dict) -> str:
    emoji, status_text = server_status(server)

    sip = server.get("server_ip") or ""
    ip_display = f"<code>{sip}</code>" if sip else "Не привязан"

    # Telegram info
    dev_ids_raw = server.get("dev_telegram_ids", "") or ""
    first_dev_id = dev_ids_raw.split(",")[0].strip() if dev_ids_raw else "—"
    bot_username = server.get("bot_username", "") or ""
    bot_link = f"@{bot_username}" if bot_username else "—"

    created = "—"
    try:
        dt = datetime.fromisoformat(server["created_at"])
        created = dt.strftime("%d.%m.%Y")
    except Exception:
        pass

    if not server.get("expires_at"):
        expires = "♾️"
    else:
        try:
            dt = datetime.fromisoformat(server["expires_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_msk = dt + MSK_OFFSET
            expires = dt_msk.strftime("%d.%m.%Y %H:%M") + " (МСК)"
        except Exception:
            expires = "—"

    period_code = server.get("period") or "—"
    period_label = PERIOD_LABELS.get(period_code, period_code)
    if period_code == "unlimited":
        period_label = "♾️"

    key = server.get("license_key", "—")

    return (
        f"Сервер: <b>{server['name']}</b>\n"
        f"Статус: {emoji} <b>{status_text}</b>\n"
        f"Телеграм ID: <code>{first_dev_id}</code>\n"
        f"Телеграм бот: {bot_link}\n"
        f"🌐 IP: {ip_display}\n"
        f"\n"
        f"🔑 Ключ: <code>{key}</code>\n"
        f"\n"
        f"📅 Добавлен: {created}\n"
        f"⏳ Истекает: {expires}\n"
        f"🗓 Длительность: {period_label}"
    )


def _clients_header(count: int) -> str:
    return f"📋 <b>Список серверов:</b> {_pluralize_servers(count)}"


async def _clear_confirm(state: FSMContext, bot: Bot, chat_id: int):
    data = await state.get_data()
    msg_id = data.get("confirm_msg_id")
    if msg_id:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    keys_to_keep = {k: v for k, v in data.items()
                    if k not in ("confirm_delete", "confirm_blacklist", "confirm_msg_id")}
    await state.set_data(keys_to_keep)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not _is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())


@router.callback_query(F.data == "main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.message.edit_text("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
    await call.answer()


# ── Список клиентов ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "clients")
async def cb_clients(call: CallbackQuery, state: FSMContext, db: Database):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    await call.message.edit_text(_clients_header(len(servers)), reply_markup=clients_kb(servers))
    await call.answer()


# ── Отмена добавления ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_add")
async def cb_cancel_add(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    await call.message.edit_text(_clients_header(len(servers)), reply_markup=clients_kb(servers))
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
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main")]
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
    await call.message.edit_text(_clients_header(len(servers)), reply_markup=clients_kb(servers))
    await call.answer("▶️ Возобновлён" if new_active else "⏸ Приостановлен")


# ── Добавить сервер ────────────────────────────────────────────────────────────

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

    # Определяем откуда пришли — если предыдущее сообщение содержит "Список серверов",
    # значит пользователь нажал дату в списке
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
        await call.message.edit_text(_clients_header(len(servers)), reply_markup=clients_kb(servers))
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
                                     [InlineKeyboardButton(text="❌ Отмена", callback_data=f"s:{server_id}")]
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


# ── Отправить сообщение ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("msg:"))
async def cb_send_message(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _clear_confirm(state, call.bot, call.message.chat.id)
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    bot_token = server.get("bot_token", "") or ""
    dev_ids = server.get("dev_telegram_ids", "") or ""
    if not bot_token or not dev_ids:
        await call.answer("❌ Нет данных бота. Дождитесь проверки лицензии клиентом.", show_alert=True)
        return
    await state.set_state(SendMessageState.waiting_text)
    await state.update_data(server_id=server_id,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text(
        f"✉️ Введите сообщение для <b>{server['name']}</b>:\n\n"
        f"Сообщение будет отправлено DEV-пользователям бота.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"s:{server_id}")]
        ]),
    )
    await call.answer()


@router.message(SendMessageState.waiting_text)
async def on_send_message_text(message: Message, state: FSMContext, db: Database):
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

    server = await db.get_server(server_id)
    if not server:
        try:
            await message.bot.edit_message_text("Сервер не найден.", chat_id=chat_id,
                                                 message_id=prompt_msg_id)
        except Exception:
            await message.answer("Сервер не найден.")
        return

    bot_token = server.get("bot_token", "") or ""
    dev_ids_raw = server.get("dev_telegram_ids", "") or ""
    dev_ids = [tid.strip() for tid in dev_ids_raw.split(",") if tid.strip()]

    if not bot_token or not dev_ids:
        text = "❌ Нет данных бота для отправки."
    else:
        msg_text = (
            "📩 <b>Сообщение от администратора лицензий</b>\n\n"
            f"{message.text}"
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
                                {"text": "✅ Закрыть", "callback_data": "license_warning_close"}
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
        text = f"✅ Сообщение отправлено ({sent_ok}/{len(dev_ids)})\n\n{format_server(server)}"

    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id,
                                                 reply_markup=server_detail_kb(server))
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=server_detail_kb(server) if server else None)


# ── Настройки ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    await call.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=settings_kb(interval, grace))
    await call.answer()


# ── Интервал проверки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_check_interval")
async def cb_settings_interval(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsIntervalState.waiting_interval)
    await call.message.edit_text("🔄 Введите интервал проверки в <b>минутах</b> (1–1440):")
    await call.answer()


@router.message(SettingsIntervalState.waiting_interval)
async def on_interval_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 1440:
            raise ValueError
    except ValueError:
        return await message.answer("❌ Введите число от 1 до 1440.")
    await db.set_check_interval(val)
    await state.clear()
    grace = await db.get_offline_grace_days()
    await message.answer(
        f"✅ Интервал обновлён: <b>{val} мин.</b>\n\n⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(val, grace),
    )


# ── Офлайн-период ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_offline_grace")
async def cb_settings_offline_grace(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsOfflineGraceState.waiting_days)
    await call.message.edit_text(
        "📡 Введите количество <b>дней</b> автономной работы (1–365):"
    )
    await call.answer()


@router.message(SettingsOfflineGraceState.waiting_days)
async def on_offline_grace_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 365:
            raise ValueError
    except ValueError:
        return await message.answer("❌ Введите число от 1 до 365.")
    await db.set_offline_grace_days(val)
    await state.clear()
    interval = await db.get_check_interval()
    await message.answer(
        f"✅ Автономность обновлена: <b>{val} дн.</b>\n\n⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(interval, val),
    )


# ── Бэкап ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "backup_menu")
async def cb_backup_menu(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.message.edit_text("💾 <b>Бэкап базы данных</b>", reply_markup=backup_kb())
    await call.answer()


@router.callback_query(F.data == "backup_save")
async def cb_backup_save(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.answer("⏳ Создаём бэкап...")
    data = await db.export_backup()
    buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode())
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    await call.message.answer_document(
        BufferedInputFile(buf.read(), filename=f"backup_{ts}.json"),
        caption="✅ Бэкап готов",
        reply_markup=backup_kb(),
    )


@router.callback_query(F.data == "backup_load")
async def cb_backup_load(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state("backup_upload")
    await call.message.edit_text("📤 Отправьте JSON-файл бэкапа:")
    await call.answer()


@router.message(F.document, F.from_user.func(lambda u: u.id == BOT_ADMIN_ID))
async def backup_load(message: Message, state: FSMContext, db: Database):
    current_state = await state.get_state()
    if current_state != "backup_upload":
        return
    doc: Document = message.document
    if not doc.file_name.endswith(".json"):
        return await message.answer("❌ Нужен JSON-файл.")
    buf = io.BytesIO()
    await message.bot.download(doc, destination=buf)
    buf.seek(0)
    try:
        data = json.load(buf)
    except Exception:
        return await message.answer("❌ Ошибка чтения файла.")
    try:
        await db.import_backup(data)
    except Exception as e:
        return await message.answer(f"❌ Ошибка импорта: {e}")
    await state.clear()
    servers = await db.get_all_servers()
    await message.answer(
        f"✅ Бэкап восстановлен\n\n{_clients_header(len(servers))}",
        reply_markup=clients_kb(servers),
    )
