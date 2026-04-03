from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timezone
import os
import shutil
import tempfile

from config import BOT_ADMIN_ID, DATABASE_PATH
from database import LicenseDB, PERIODS
from bot.keyboards import (
    main_menu_kb,
    period_kb,
    server_detail_kb,
    confirm_delete_kb,
    server_status,
    admin_kb,
    backup_kb,
    settings_kb,
)

router = Router()


class RenameState(StatesGroup):
    waiting_name = State()


class BackupRestoreState(StatesGroup):
    waiting_file = State()


class SettingsState(StatesGroup):
    waiting_interval = State()


def format_date(iso_str) -> str:
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
    ip = server["server_ip"] or "Не привязан"
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
        f"🌐 IP сервера: <code>{ip}</code>\n"
        f"📅 Создан: {format_date(server['created_at'])}\n"
        f"⏰ Действует до: {expires}\n"
        f"📊 Статус: {emoji} {status_text}\n"
        f"📋 Тариф: {period_text}\n"
        f"🔄 Последняя проверка: {last_check}"
    )


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


@router.callback_query(F.data.startswith("rip:"))
async def cb_reset_ip(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    server_id = int(callback.data.split(":")[1])
    server = await db.reset_ip(server_id)
    if not server:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔓 IP сброшен\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )
    await callback.answer()


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
            await message.answer(format_server(server), reply_markup=server_detail_kb(server))
        return

    server = await db.rename_server(server_id, new_name)
    if not server:
        await message.answer("Сервер не найден")
        return
    await message.answer(
        f"✅ Сервер переименован\n\n{format_server(server)}",
        reply_markup=server_detail_kb(server),
    )


@router.callback_query(F.data == "admin")
async def cb_admin(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await callback.message.edit_text("⚙️ <b>Администрирование</b>", reply_markup=admin_kb())
    await callback.answer()


@router.callback_query(F.data == "backup_menu")
async def cb_backup_menu(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await callback.message.edit_text("💾 <b>Управление бэкапами</b>", reply_markup=backup_kb())
    await callback.answer()


@router.callback_query(F.data == "backup_save")
async def cb_backup_save(callback: CallbackQuery):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    db_path = DATABASE_PATH
    if not os.path.isfile(db_path):
        await callback.answer("❌ База данных не найдена", show_alert=True)
        return
    try:
        tmp_dir = tempfile.mkdtemp()
        archive_base = os.path.join(tmp_dir, "license-backup")
        backup_dir = os.path.join(tmp_dir, "backup")
        os.makedirs(backup_dir)
        shutil.copy2(db_path, os.path.join(backup_dir, "license.db"))
        archive_path = shutil.make_archive(archive_base, "zip", backup_dir)
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"license-backup_{now}.zip"
        with open(archive_path, "rb") as f:
            file_data = f.read()
        doc = BufferedInputFile(file_data, filename=filename)
        await callback.message.answer_document(doc, caption=f"💾 Бэкап базы лицензий\n📅 {now}")
        await callback.answer("✅ Бэкап создан")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.callback_query(F.data == "backup_load")
async def cb_backup_load(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await state.set_state(BackupRestoreState.waiting_file)
    await callback.message.edit_text(
        "📤 <b>Отправьте файл архива бэкапа (.zip)</b>\n\n⚠️ Текущая база будет заменена!",
    )
    await callback.answer()


@router.message(BackupRestoreState.waiting_file, F.document)
async def on_backup_file(message: Message, db: LicenseDB, state: FSMContext):
    if message.from_user.id != BOT_ADMIN_ID:
        return
    doc = message.document
    if not doc.file_name.endswith(".zip"):
        await message.answer("❌ Отправьте файл в формате .zip")
        return
    try:
        tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, "backup.zip")
        bot = message.bot
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, zip_path)
        extract_dir = os.path.join(tmp_dir, "extracted")
        shutil.unpack_archive(zip_path, extract_dir)
        db_file = None
        for root, dirs, files in os.walk(extract_dir):
            if "license.db" in files:
                db_file = os.path.join(root, "license.db")
                break
        if not db_file:
            await message.answer("❌ Файл license.db не найден в архиве")
            await state.clear()
            return
        shutil.copy2(db_file, DATABASE_PATH)
        await db.init()
        await state.clear()
        servers = await db.get_all_servers()
        await message.answer(
            f"✅ Бэкап восстановлен!\n\nВ базе {len(servers)} серверов.\n\n🔑 <b>Управление лицензиями</b>",
            reply_markup=main_menu_kb(servers),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка восстановления: {e}")
        await state.clear()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.message(BackupRestoreState.waiting_file)
async def on_backup_not_file(message: Message):
    if message.from_user.id != BOT_ADMIN_ID:
        return
    await message.answer("❌ Пожалуйста, отправьте файл архива (.zip)")


@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(callback: CallbackQuery, db: LicenseDB):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    interval = await db.get_check_interval()
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=settings_kb(interval))
    await callback.answer()


@router.callback_query(F.data == "settings_check_interval")
async def cb_settings_check_interval(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != BOT_ADMIN_ID:
        return
    await state.set_state(SettingsState.waiting_interval)
    await callback.message.edit_text(
        "🔄 <b>Частота проверки лицензии</b>\n\nВведите интервал в минутах (минимум 1):"
    )
    await callback.answer()


@router.message(SettingsState.waiting_interval)
async def on_interval_input(message: Message, db: LicenseDB, state: FSMContext):
    if message.from_user.id != BOT_ADMIN_ID:
        return
    text = message.text.strip()
    try:
        minutes = int(text)
        if minutes < 1:
            raise ValueError()
    except (ValueError, TypeError):
        await message.answer("❌ Введите целое число минут (минимум 1)")
        return
    await db.set_check_interval(minutes)
    await state.clear()
    interval = await db.get_check_interval()
    await message.answer(
        f"✅ Частота проверки установлена: <b>{interval} мин.</b>\n\n⚙️ <b>Настройки</b>",
        reply_markup=settings_kb(interval),
    )
