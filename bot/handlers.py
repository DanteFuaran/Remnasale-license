import io
import json
import sqlite3
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    Document,
)
from datetime import datetime, timezone

from config import BOT_ADMIN_ID
from database import Database
from bot.keyboards import (
    main_menu_kb, clients_kb, period_kb,
    server_detail_kb, confirm_delete_kb, backup_kb, settings_kb,
    server_status,
)

router = Router()


class AddServerState(StatesGroup):
    waiting_name = State()
    waiting_period = State()


class RenameState(StatesGroup):
    waiting_name = State()


class SettingsIntervalState(StatesGroup):
    waiting_interval = State()


class SettingsOfflineGraceState(StatesGroup):
    waiting_days = State()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


def format_server(server: dict) -> str:
    emoji, status_text = server_status(server)
    sip = server.get("server_ip") or "—"
    created = ""
    try:
        dt = datetime.fromisoformat(server["created_at"])
        created = dt.strftime("%d.%m.%Y")
    except Exception:
        created = "—"
    expires = ""
    if not server["expires_at"]:
        expires = "♾ Бессрочно"
    else:
        try:
            dt = datetime.fromisoformat(server["expires_at"])
            expires = dt.strftime("%d.%m.%Y %H:%M") + " UTC"
        except Exception:
            expires = "—"
    period_label = server.get("period", "—") or "—"
    key = server.get("license_key", "—")

    lines = [
        f"{emoji} <b>{server['name']}</b>",
        "",
        f"🔑 Ключ: <code>{key}</code>",
        f"🌐 IP: <code>{sip}</code>",
        f"📅 Добавлен: {created}",
        f"⏳ Истекает: {expires}",
        f"🗓 Тариф: {period_label}",
    ]
    return "\n".join(lines)


# ── /start ──────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not _is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer(
        "🔑 <b>Управление лицензиями</b>",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.message.edit_text(
        "🔑 <b>Управление лицензиями</b>",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ── Список клиентов ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "clients")
async def cb_clients(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    text = f"📋 <b>Клиенты</b> — {len(servers)} сервер(ов)"
    await call.message.edit_text(text, reply_markup=clients_kb(servers))
    await call.answer()


# ── Статистика ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    servers = await db.get_all_servers()
    total = len(servers)
    now = datetime.now(timezone.utc)
    active = 0
    expired = 0
    paused = 0
    blacklisted = 0
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

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Всего серверов: <b>{total}</b>\n"
        f"🟢 Активных: <b>{active}</b>\n"
        f"🟡 Истекших: <b>{expired}</b>\n"
        f"🔴 Приостановлено: <b>{paused}</b>\n"
        f"❌ Заблокировано: <b>{blacklisted}</b>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# ── Карточка сервера ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("s:"))
async def cb_server_detail(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(
        format_server(server),
        reply_markup=server_detail_kb(server),
    )
    await call.answer()


# ── Добавить сервер ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "add")
async def cb_add_server(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AddServerState.waiting_name)
    await call.message.edit_text(
        "✏️ Введите название сервера:",
        reply_markup=None,
    )
    await call.answer()


@router.message(AddServerState.waiting_name)
async def on_server_name(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AddServerState.waiting_period)
    await message.answer(
        "🗓 Выберите тариф:",
        reply_markup=period_kb("ap"),
    )


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


# ── Продлить ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ext:"))
async def cb_extend(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await state.update_data(server_id=server_id)
    await call.message.edit_text(
        "🗓 Выберите новый тариф:",
        reply_markup=period_kb(f"ep"),
    )
    await state.update_data(server_id=server_id)
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


# ── Сбросить IP ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rip:"))
async def cb_reset_ip(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.reset_server_ip(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer("✅ IP сброшен")


# ── Приостановить / Возобновить ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("tog:"))
async def cb_toggle(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    new_active = 0 if server["is_active"] else 1
    server = await db.set_server_active(server_id, new_active)
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    status = "возобновлён" if new_active else "приостановлен"
    await call.answer(f"{'▶️' if new_active else '⏸'} Сервер {status}")


# ── Заблокировать / Разблокировать ────────────────────────────────────────────

@router.callback_query(F.data.startswith("blk:"))
async def cb_blacklist(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    if server.get("is_blacklisted"):
        server = await db.unblacklist_server(server_id)
        msg = "🔓 Сервер разблокирован"
    else:
        server = await db.blacklist_server(server_id)
        msg = "🚫 Сервер заблокирован"
    await call.message.edit_text(format_server(server), reply_markup=server_detail_kb(server))
    await call.answer(msg)


# ── Переименовать ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ren:"))
async def cb_rename(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await state.set_state(RenameState.waiting_name)
    await state.update_data(server_id=server_id)
    await call.message.edit_text("✏️ Введите новое название сервера:")
    await call.answer()


@router.message(RenameState.waiting_name)
async def on_rename(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    server_id = data.get("server_id")
    await state.clear()
    server = await db.rename_server(server_id, message.text.strip())
    if not server:
        await message.answer("Сервер не найден.")
        return
    await message.answer(format_server(server), reply_markup=server_detail_kb(server))


# ── Удалить ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return
    await call.message.edit_text(
        f"🗑 Удалить сервер <b>{server['name']}</b>?\n\nЭто действие нельзя отменить.",
        reply_markup=confirm_delete_kb(server_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cdel:"))
async def cb_confirm_delete(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    server_id = int(call.data.split(":")[1])
    await db.delete_server(server_id)
    servers = await db.get_all_servers()
    text = f"📋 <b>Клиенты</b> — {len(servers)} сервер(ов)"
    await call.message.edit_text(text, reply_markup=clients_kb(servers))
    await call.answer("🗑 Удалено")


# ── Настройки ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    await call.message.edit_text(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(interval, grace),
    )
    await call.answer()


# ── Интервал проверки ─────────────────────────────────────────────────────────

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


# ── Офлайн-период ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_offline_grace")
async def cb_settings_offline_grace(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsOfflineGraceState.waiting_days)
    await call.message.edit_text(
        "📡 Введите количество <b>дней</b> автономной работы клиентов при недоступности сервера лицензий (1–365):"
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


# ── Бэкап ──────────────────────────────────────────────────────────────────────

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
    text = f"✅ Бэкап восстановлен\n\n📋 <b>Клиенты</b> — {len(servers)} сервер(ов)"
    await message.answer(text, reply_markup=clients_kb(servers))
