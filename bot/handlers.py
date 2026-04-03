from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timezone

from config import BOT_ADMIN_ID
from database import LicenseDB, PERIODS
from bot.keyboards import (
    main_menu_kb,
    period_kb,
    server_detail_kb,
    confirm_delete_kb,
    server_status,
)

router = Router()


class RenameState(StatesGroup):
    waiting_name = State()


def format_date(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return "—"


def format_server(server: dict) -> str:
    emoji, status_text = server_status(server)
    domain = server["server_domain"] or "Не привязан"
    expires = "♾ Бессрочно" if not server["expires_at"] else format_date(server["expires_at"])
    last_check = format_date(server["last_check_at"])

    period_labels = {
        "1m": "1 месяц",
        "3m": "3 месяца",
        "6m": "6 месяцев",
        "12m": "12 месяцев",
        "unlimited": "Бессрочно",
    }
    period_text = period_labels.get(server["period"], server["period"])

    return (
        f"📊 <b>{server['name']}</b>\n\n"
        f"🔑 Ключ:\n<code>{server['license_key']}</code>\n\n"
        f"🌐 Домен: <code>{domain}</code>\n"
        f"📅 Создан: {format_date(server['created_at'])}\n"
        f"⏰ Действует до: {expires}\n"
        f"📊 Статус: {emoji} {status_text}\n"
        f"📋 Тариф: {period_text}\n"
        f"🔄 Последняя проверка: {last_check}"
    )


# === START ===

@router.message(CommandStart())
async def cmd_start(message: Message, db: LicenseDB, state: FSMContext):
    if message.from_user.id != BOT_ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.clear()
    servers = await db.get_all_servers()
    await message.answer(
        "🔑 <b>Управление лицензиями</b>",
        reply_markup=main_menu_kb(servers),
    )


# === MAIN MENU ===

@router.callback_query(F.data == "main")
async def cb_main_menu(callback: CallbackQuery, db: LicenseDB, state: FSMContext):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await state.clear()
    servers = await db.get_all_servers()
    await callback.message.edit_text(
        "🔑 <b>Управление лицензиями</b>",
        reply_markup=main_menu_kb(servers),
    )
    await callback.answer()


# === VIEW SERVER ===

@router.callback_query(F.data.startswith("s:"))
async def cb_server_detail(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    server = await db.get_server(server_id)
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    await callback.message.edit_text(
        format_server(server),
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


# === ADD SERVER ===

@router.callback_query(F.data == "add")
async def cb_add_server(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await callback.message.edit_text(
        "📅 <b>Выберите срок действия лицензии:</b>",
        reply_markup=period_kb("ap"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ap:"))
async def cb_add_with_period(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    period = callback.data.split(":")[1]
    server = await db.add_server(period)
    await callback.message.edit_text(
        f"✅ Сервер создан!\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


# === EXTEND ===

@router.callback_query(F.data.startswith("ext:"))
async def cb_extend(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = callback.data.split(":")[1]
    await callback.message.edit_text(
        "📅 <b>Выберите срок продления:</b>",
        reply_markup=period_kb(f"ep:{server_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ep:"))
async def cb_extend_with_period(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    parts = callback.data.split(":")
    server_id = int(parts[1])
    period = parts[2]
    server = await db.extend_server(server_id, period)
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"✅ Лицензия продлена!\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


# === TOGGLE ===

@router.callback_query(F.data.startswith("tog:"))
async def cb_toggle(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    server = await db.toggle_server(server_id)
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    status = "возобновлён" if server["is_active"] else "приостановлен"
    emoji = "▶️" if server["is_active"] else "⏸"
    await callback.message.edit_text(
        f"{emoji} Сервер {status}\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


# === RESET DOMAIN ===

@router.callback_query(F.data.startswith("rip:"))
async def cb_reset_domain(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    server = await db.reset_domain(server_id)
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔓 Домен сброшен\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


# === DELETE ===

@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        "🗑 <b>Удалить сервер?</b>\n\nЭто действие необратимо.",
        reply_markup=confirm_delete_kb(server_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cdel:"))
async def cb_confirm_delete(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    await db.delete_server(server_id)
    servers = await db.get_all_servers()
    await callback.message.edit_text(
        "🗑 Сервер удалён.\n\n🔑 <b>Управление лицензиями</b>",
        reply_markup=main_menu_kb(servers),
    )
    await callback.answer()


# === RENAME ===

@router.callback_query(F.data.startswith("ren:"))
async def cb_rename_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    await state.set_state(RenameState.waiting_name)
    await state.update_data(server_id=server_id)
    await callback.message.edit_text("✏️ <b>Введите новое имя сервера:</b>")
    await callback.answer()


@router.message(RenameState.waiting_name)
async def on_rename_input(message: Message, db: LicenseDB, state: FSMContext):
    if message.from_user.id != BOT_ADMIN_ID:
        return
    data = await state.get_data()
    server_id = data["server_id"]
    new_name = message.text.strip()[:50]
    await state.clear()

    if not new_name:
        server = await db.get_server(server_id)
        if server:
            await message.answer(
                format_server(server),
                reply_markup=server_detail_kb(server),
            )
        return

    server = await db.rename_server(server_id, new_name)
    if not server:
        await message.answer("Сервер не найден")
        return

    await message.answer(
        f"✅ Сервер переименован\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
