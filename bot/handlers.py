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

from config import BOT_ADMIN_ID, PUBLIC_URL
from database import Database
from bot.keyboards import (
    main_menu_kb, clients_kb, period_kb, add_period_kb, cancel_kb,
    server_detail_kb, backup_kb, settings_kb, compose_kb,
    user_servers_kb, user_server_kb, setting_edit_kb, setting_edit_pending_kb,
    sync_kb, payments_kb, gateway_detail_kb, gateway_placement_kb, gateway_currency_kb,
    server_status, PERIOD_LABELS,
    user_view_servers_kb, user_view_server_kb, user_view_empty_kb,
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


class SettingsSupportUrlState(StatesGroup):
    waiting_url = State()


class SettingsCommunityUrlState(StatesGroup):
    waiting_url = State()


class SendMessageState(StatesGroup):
    composing = State()
    waiting_text = State()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


def format_user_server(server: dict) -> str:
    emoji, status_text = server_status(server)

    name = server.get("name", "") or "Отсутствует"

    dev_ids_raw = server.get("dev_telegram_ids", "") or ""
    first_dev_id = dev_ids_raw.split(",")[0].strip() if dev_ids_raw else ""
    tg_id_display = first_dev_id if first_dev_id else "Отсутствует"

    bot_username = server.get("bot_username", "") or ""
    bot_link = f"@{bot_username}" if bot_username else "Отсутствует"

    remnasale_ver = server.get("remnasale_version", "") or ""
    ver_suffix = f" {remnasale_ver}" if remnasale_ver else ""

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
        f"👤 <b>Профиль</b>\n"
        f"<blockquote>👤 Имя: {name}\n"
        f"📱 Телеграм ID: {tg_id_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Remnasale{ver_suffix}</b>\n"
        f"<blockquote>{emoji} Статус: {status_text}\n"
        f"🤖 Телеграм бот: {bot_link}</blockquote>\n"
        f"\n"
        f"📦 <b>Support</b>\n"
        f"<blockquote>⭕ Статус: Не куплено\n"
        f"🤖 Телеграм бот: Отсутствует\n"
        f"🌐 IP: Отсутствует</blockquote>\n"
        f"\n"
        f"🔑 Ключ: <code>{key}</code>\n"
        f"<blockquote>📅 Добавлен: {created}\n"
        f"⏳ Истекает: {expires}\n"
        f"🗓 Длительность: {period_label}</blockquote>"
    )


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

    name = server.get("name", "") or "Отсутствует"

    sip = server.get("server_ip") or ""
    ip_display = f"<code>{sip}</code>" if sip else "Отсутствует"

    dev_ids_raw = server.get("dev_telegram_ids", "") or ""
    first_dev_id = dev_ids_raw.split(",")[0].strip() if dev_ids_raw else ""
    tg_id_display = f"<code>{first_dev_id}</code>" if first_dev_id else "Отсутствует"

    bot_username = server.get("bot_username", "") or ""
    bot_link = f"@{bot_username}" if bot_username else "Отсутствует"

    remnasale_ver = server.get("remnasale_version", "") or ""
    ver_suffix = f" {remnasale_ver}" if remnasale_ver else ""

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
        f"👤 <b>Профиль</b>\n"
        f"<blockquote>👤 Имя: {name}\n"
        f"📱 Телеграм ID: {tg_id_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Remnasale{ver_suffix}</b>\n"
        f"<blockquote>{emoji} Статус: {status_text}\n"
        f"🤖 Телеграм бот: {bot_link}\n"
        f"🌐 IP: {ip_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Support</b>\n"
        f"<blockquote>⭕ Статус: Не куплено\n"
        f"🤖 Телеграм бот: Отсутствует\n"
        f"🌐 IP: Отсутствует</blockquote>\n"
        f"\n"
        f"🔑 Ключ: <code>{key}</code>\n"
        f"<blockquote>📅 Добавлен: {created}\n"
        f"⏳ Истекает: {expires}\n"
        f"🗓 Длительность: {period_label}</blockquote>"
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
                    if k not in ("confirm_delete", "confirm_blacklist", "confirm_send", "confirm_msg_id")}
    await state.set_data(keys_to_keep)


async def _settings_kb_full(db: Database) -> InlineKeyboardMarkup:
    return settings_kb()


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    if _is_admin(message.from_user.id):
        return await message.answer("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
    # Check if user is a dev for any server
    servers = await db.find_servers_by_dev_id(message.from_user.id)
    if not servers:
        return await message.answer("⛔ Нет доступа.")
    if len(servers) == 1:
        server = servers[0]
        support = await db.get_setting("support_url")
        community = await db.get_setting("community_url")
        return await message.answer(
            format_user_server(server),
            reply_markup=user_server_kb(server, support, community),
        )
    await message.answer(
        "🖥️ <b>Ваши серверы:</b>",
        reply_markup=user_servers_kb(servers),
    )


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


@router.callback_query(F.data == "main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await _clear_confirm(state, call.bot, call.message.chat.id)
    await state.clear()
    if _is_admin(call.from_user.id):
        await call.message.edit_text("🔑 <b>Управление лицензиями</b>", reply_markup=main_menu_kb())
        return await call.answer()
    # User role — show their servers
    servers = await db.find_servers_by_dev_id(call.from_user.id)
    if not servers:
        return await call.answer("⛔")
    if len(servers) == 1:
        server = servers[0]
        support = await db.get_setting("support_url")
        community = await db.get_setting("community_url")
        await call.message.edit_text(
            format_user_server(server),
            reply_markup=user_server_kb(server, support, community),
        )
    else:
        await call.message.edit_text(
            "🖥️ <b>Ваши серверы:</b>",
            reply_markup=user_servers_kb(servers),
        )
    await call.answer()


# ── Панель пользователя ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("us:"))
async def cb_user_server(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    # Verify user has access
    dev_ids = (server.get("dev_telegram_ids", "") or "").split(",")
    if str(call.from_user.id) not in [t.strip() for t in dev_ids]:
        return await call.answer("⛔")
    support = await db.get_setting("support_url")
    community = await db.get_setting("community_url")
    await call.message.edit_text(
        format_user_server(server),
        reply_markup=user_server_kb(server, support, community),
    )
    await call.answer()


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
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary")]
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


# ── Написать сообщение (compose flow) ──────────────────────────────────────────

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
        await call.answer("Сервер не найден", show_alert=True)
        return
    bot_token = server.get("bot_token", "") or ""
    dev_ids = server.get("dev_telegram_ids", "") or ""
    if not bot_token or not dev_ids:
        await call.answer("❌ Нет данных бота. Дождитесь проверки лицензии клиентом.", show_alert=True)
        return
    await state.set_state(SendMessageState.composing)
    await state.update_data(server_id=server_id, compose_text=None,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text(
        _compose_header(server, None),
        reply_markup=compose_kb(server_id, has_text=False),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cmt:"))
async def cb_compose_enter_text(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await state.set_state(SendMessageState.waiting_text)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text(
        "📝 Введите текст сообщения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"msg:{server_id}", style="danger")]
        ]),
    )
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
        await call.answer("Нет текста для предпросмотра", show_alert=True)
        return
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    # Send preview as a separate message (as client would see it)
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
        await call.answer("Нет текста для отправки", show_alert=True)
        return

    # Double-click confirm
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
            await call.answer("Сервер не найден", show_alert=True)
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
        await call.message.edit_text(
            f"✅ Сообщение отправлено ({sent_ok}/{len(dev_ids)})\n\n{format_server(server)}",
            reply_markup=server_detail_kb(server),
        )
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


# ── Настройки ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=await _settings_kb_full(db))
    await call.answer()


# ── Настройка синхронизации ────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_sync")
async def cb_settings_sync(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    await call.message.edit_text(
        "🔄 <b>Настройка синхронизации</b>",
        reply_markup=sync_kb(interval, grace),
    )
    await call.answer()


# ── Интервал проверки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_check_interval")
async def cb_settings_interval(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsIntervalState.waiting_interval)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text(
        "🔄 Введите интервал проверки в <b>минутах</b> (1–1440):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_sync", style="primary")]
        ]),
    )
    await call.answer()


@router.message(SettingsIntervalState.waiting_interval)
async def on_interval_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 1440:
            raise ValueError
    except ValueError:
        return
    await db.set_check_interval(val)
    data = await state.get_data()
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    text = f"✅ Интервал: <b>{val} мин.</b>\n\n🔄 <b>Настройка синхронизации</b>"
    kb = sync_kb(interval, grace)
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


# ── Офлайн-период ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_offline_grace")
async def cb_settings_offline_grace(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsOfflineGraceState.waiting_days)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await call.message.edit_text(
        "📡 Введите количество <b>дней</b> автономной работы (1–365):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_sync", style="primary")]
        ]),
    )
    await call.answer()


@router.message(SettingsOfflineGraceState.waiting_days)
async def on_offline_grace_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    try:
        val = int(message.text.strip())
        if not 1 <= val <= 365:
            raise ValueError
    except ValueError:
        return
    await db.set_offline_grace_days(val)
    data = await state.get_data()
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    text = f"✅ Автономность: <b>{val} дн.</b>\n\n🔄 <b>Настройка синхронизации</b>"
    kb = sync_kb(interval, grace)
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


# ── Настройка поддержки ────────────────────────────────────────────────────────

def _support_edit_text(current: str) -> str:
    display = current or "Не указана"
    return (
        "🆘 <b>Настройка помощи</b>\n\n"
        f"<blockquote>🆘 Помощь: {display}</blockquote>\n\n"
        "ℹ️ <i>Введите имя бота или группы помощи без https://t.me "
        "(например <b>support_bot</b>).</i>"
    )


@router.callback_query(F.data == "settings_support_url")
async def cb_settings_support_url(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = await db.get_setting("support_url")
    await state.set_state(SettingsSupportUrlState.waiting_url)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id,
                            pending_value=None, original_value=current)
    await call.message.edit_text(
        _support_edit_text(current),
        reply_markup=setting_edit_kb("clear_support", "settings_menu"),
    )
    await call.answer()


@router.callback_query(F.data == "clear_support")
async def cb_clear_support(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("support_url", "")
    await state.clear()
    await call.message.edit_text(
        "✅ Поддержка очищена\n\n⚙️ <b>Настройки</b>",
        reply_markup=await _settings_kb_full(db),
    )
    await call.answer()


@router.callback_query(F.data == "accept_support")
async def cb_accept_support(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    val = data.get("pending_value") or ""
    await db.set_setting("support_url", val)
    await state.clear()
    await call.message.edit_text(
        f"✅ Поддержка: <b>{val}</b>\n\n⚙️ <b>Настройки</b>",
        reply_markup=await _settings_kb_full(db),
    )
    await call.answer()


@router.message(SettingsSupportUrlState.waiting_url)
async def on_support_url_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    raw = message.text.strip().removeprefix("https://t.me/").removeprefix("http://t.me/").removeprefix("t.me/").removeprefix("@")
    await state.update_data(pending_value=raw)
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    text = _support_edit_text(raw)
    kb = setting_edit_pending_kb("accept_support", "clear_support", "settings_menu")
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


# ── Настройка сообщества ──────────────────────────────────────────────────────

def _community_edit_text(current: str) -> str:
    display = current or "Не указано"
    return (
        "👥 <b>Настройка сообщества</b>\n\n"
        f"<blockquote>👥 Сообщество: {display}</blockquote>\n\n"
        "ℹ️ <i>Введите ссылку сообщества (группы) без https://t.me "
        "(например <b>support_group</b>).</i>"
    )


@router.callback_query(F.data == "settings_community_url")
async def cb_settings_community_url(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = await db.get_setting("community_url")
    await state.set_state(SettingsCommunityUrlState.waiting_url)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id,
                            pending_value=None, original_value=current)
    await call.message.edit_text(
        _community_edit_text(current),
        reply_markup=setting_edit_kb("clear_community", "settings_menu"),
    )
    await call.answer()


@router.callback_query(F.data == "clear_community")
async def cb_clear_community(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("community_url", "")
    await state.clear()
    await call.message.edit_text(
        "✅ Сообщество очищено\n\n⚙️ <b>Настройки</b>",
        reply_markup=await _settings_kb_full(db),
    )
    await call.answer()


@router.callback_query(F.data == "accept_community")
async def cb_accept_community(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    val = data.get("pending_value") or ""
    await db.set_setting("community_url", val)
    await state.clear()
    await call.message.edit_text(
        f"✅ Сообщество: <b>{val}</b>\n\n⚙️ <b>Настройки</b>",
        reply_markup=await _settings_kb_full(db),
    )
    await call.answer()


@router.message(SettingsCommunityUrlState.waiting_url)
async def on_community_url_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    raw = message.text.strip().removeprefix("https://t.me/").removeprefix("http://t.me/").removeprefix("t.me/").removeprefix("@")
    await state.update_data(pending_value=raw)
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    text = _community_edit_text(raw)
    kb = setting_edit_pending_kb("accept_community", "clear_community", "settings_menu")
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


# ── Платёжные системы ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_payments")
async def cb_settings_payments(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gateways = await db.get_all_gateways()
    await call.message.edit_text("💳 <b>Платёжные системы</b>", reply_markup=payments_kb(gateways))
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


@router.callback_query(F.data.startswith("gw:"))
async def cb_gateway_detail(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.get_gateway(gtype)
    if not gw:
        await call.answer("Шлюз не найден", show_alert=True)
        return
    from database import GATEWAY_TYPES
    meta = GATEWAY_TYPES.get(gtype, {})
    label = meta.get("label", gtype)
    # Telegram Stars has no settings fields
    if not meta.get("fields"):
        await call.answer("ℹ️ Шлюз не требует настройки", show_alert=True)
        return
    await call.message.edit_text(
        _format_gateway_detail_text(gw, meta),
        reply_markup=gateway_detail_kb(gw, PUBLIC_URL),
    )
    await call.answer()


@router.callback_query(F.data.startswith("gwtest:"))
async def cb_gateway_test(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.get_gateway(gtype)
    if not gw:
        await call.answer("Шлюз не найден", show_alert=True)
        return
    from database import GATEWAY_TYPES
    meta = GATEWAY_TYPES.get(gtype, {})
    # Check if gateway is configured
    fields = meta.get("fields", {})
    settings = gw.get("settings", {})
    if fields and not all(settings.get(f) for f in fields):
        await call.answer("❌ Шлюз не настроен", show_alert=True)
        return
    if not gw["is_active"]:
        await call.answer("❌ Шлюз выключен", show_alert=True)
        return
    label = meta.get("label", gtype)
    await call.answer(f"🐞 Тестовый платёж {label}: в разработке", show_alert=True)


@router.callback_query(F.data.startswith("gwt:"))
async def cb_gateway_toggle(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gtype = call.data.split(":")[1]
    gw = await db.toggle_gateway(gtype)
    if not gw:
        await call.answer("Шлюз не найден", show_alert=True)
        return
    status = "🟢 Включён" if gw["is_active"] else "🔴 Выключен"
    gateways = await db.get_all_gateways()
    await call.message.edit_text("💳 <b>Платёжные системы</b>", reply_markup=payments_kb(gateways))
    await call.answer(status)


class GatewayFieldState(StatesGroup):
    waiting_value = State()


@router.callback_query(F.data.startswith("gwf:"))
async def cb_gateway_field(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    parts = call.data.split(":")
    gtype, field = parts[1], parts[2]
    from database import GATEWAY_TYPES
    meta = GATEWAY_TYPES.get(gtype, {})
    field_label = meta.get("fields", {}).get(field, field)
    await state.set_state(GatewayFieldState.waiting_value)
    await state.update_data(gw_type=gtype, gw_field=field,
                            prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    gw = await db.get_gateway(gtype)
    current = (gw.get("settings", {}).get(field, "") if gw else "") or "Не указан"
    await call.message.edit_text(
        f"✏️ <b>{field_label}</b>\n\n"
        f"<blockquote>{current}</blockquote>\n\n"
        f"ℹ️ <i>Введите новое значение:</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Очистить", callback_data=f"gwfc:{gtype}:{field}", style="danger")],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"gw:{gtype}", style="primary"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary"),
            ],
        ]),
    )
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
    from database import GATEWAY_TYPES
    meta = GATEWAY_TYPES.get(gtype, {})
    await call.message.edit_text(
        _format_gateway_detail_text(gw, meta),
        reply_markup=gateway_detail_kb(gw, PUBLIC_URL),
    )
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
    from database import GATEWAY_TYPES
    meta = GATEWAY_TYPES.get(gtype, {})
    text = f"✅ Сохранено\n\n{_format_gateway_detail_text(gw, meta)}"
    kb = gateway_detail_kb(gw, PUBLIC_URL)
    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id,
                                                 message_id=prompt_msg_id, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


# ── Позиционирование шлюзов ───────────────────────────────────────────────────

@router.callback_query(F.data == "gw_placement")
async def cb_gw_placement(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    gateways = await db.get_all_gateways()
    await call.message.edit_text(
        "🔢 <b>Позиционирование платёжных систем</b>\n\n"
        "Измените порядок отображения шлюзов:",
        reply_markup=gateway_placement_kb(gateways),
    )
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
    await call.message.edit_text(
        "💸 <b>Валюта по умолчанию</b>\n\nВыберите валюту:",
        reply_markup=gateway_currency_kb(current),
    )
    await call.answer()


@router.callback_query(F.data.startswith("gwcur:"))
async def cb_gw_currency_set(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    cur = call.data.split(":")[1]
    await db.set_setting("payment_currency", cur)
    await call.message.edit_reply_markup(reply_markup=gateway_currency_kb(cur))
    await call.answer(f"✅ {cur}")


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


# ── Авто-удаление нерелевантных сообщений ─────────────────────────────────────

@router.message()
async def auto_delete_unrelated(message: Message, state: FSMContext):
    """Удаляет любое сообщение, не обработанное другими хендлерами."""
    try:
        await message.delete()
    except Exception:
        pass
