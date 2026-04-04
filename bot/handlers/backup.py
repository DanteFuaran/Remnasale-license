import io
import json
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, Document, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from config import BOT_ADMIN_ID
from database import Database
from bot.formatting import clients_header
from bot.keyboards.admin import clients_kb
from bot.keyboards.settings import backup_kb

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Закрыть", callback_data="close_backup_doc", style="success")],
        ]),
    )


@router.callback_query(F.data == "close_backup_doc")
async def cb_close_backup_doc(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


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
        f"✅ Бэкап восстановлен\n\n{clients_header(len(servers))}",
        reply_markup=clients_kb(servers),
    )
