import asyncio
import io
import json
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, Document, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone, timedelta

from config import BOT_ADMIN_ID
from database import Database
from bot.formatting import clients_header
from bot.keyboards.admin import clients_kb
from bot.keyboards.settings import backup_kb, autobackup_settings_kb, autobackup_freq_kb
from bot.states import AutoBackupTokenState, AutoBackupChatIdState
from bot.banner import show

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


@router.callback_query(F.data == "backup_menu")
async def cb_backup_menu(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    banner = await db.get_setting("banner_file_id")
    await show(call, "💾 <b>Управление БД</b>", reply_markup=backup_kb(), banner=banner or "")
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
async def cb_backup_load(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state("backup_upload")
    banner = await db.get_setting("banner_file_id")
    await show(call, "📤 Отправьте JSON-файл бэкапа:", banner=banner or "")
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


# ── Автобэкап ────────────────────────────────────────────────────────────────

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


async def _get_autobackup_settings(db: Database) -> dict:
    return {
        "enabled": await db.get_setting("autobackup_enabled", "0"),
        "silent_mode": await db.get_setting("autobackup_silent_mode", "0"),
        "bot_token": await db.get_setting("autobackup_bot_token", ""),
        "chat_id": await db.get_setting("autobackup_chat_id", ""),
        "frequency": await db.get_setting("autobackup_frequency", "daily"),
        "last_backup_at": await db.get_setting("autobackup_last_at", ""),
    }


def _autobackup_header(settings: dict) -> str:
    freq_map = {"hourly": "Каждый час", "daily": "Раз в день", "weekly": "Раз в неделю", "monthly": "Раз в месяц"}
    freq = freq_map.get(settings["frequency"], settings["frequency"])

    token_raw = settings.get("bot_token", "")
    token_display = f"{token_raw[:5]}..." if token_raw else "Не назначено"
    chat_id_display = settings.get("chat_id", "") or "Не назначено"

    last = settings.get("last_backup_at", "")
    if last:
        try:
            dt = datetime.fromisoformat(last)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            msk = dt + timedelta(hours=3)
            last_str = msk.strftime("%d.%m.%Y | %H:%M")
        except Exception:
            last_str = "—"
    else:
        last_str = "Не производился"
    return (
        f"⏰ <b>Настройка автобекапа</b>\n\n"
        f"<blockquote>• <b>Токен бота:</b> {token_display}\n"
        f"• <b>Получатель:</b> {chat_id_display}\n"
        f"• <b>Частота:</b> {freq}\n"
        f"• <b>Последний бекап:</b> {last_str}</blockquote>\n\n"
        f"<i>ℹ️ Укажите необходимые для бэкапа настройки.</i>"
    )


@router.callback_query(F.data == "autobackup_menu")
async def cb_autobackup_menu(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    settings = await _get_autobackup_settings(db)
    banner = await db.get_setting("banner_file_id")
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), banner=banner or "")
    await call.answer()


@router.callback_query(F.data == "_noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "autobackup_toggle")
async def cb_autobackup_toggle(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    new_val = "0" if settings["enabled"] == "1" else "1"
    await db.set_setting("autobackup_enabled", new_val)
    settings["enabled"] = new_val
    banner = await db.get_setting("banner_file_id")
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), banner=banner or "")
    await call.answer()


@router.callback_query(F.data == "autobackup_silent")
async def cb_autobackup_silent(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    new_val = "0" if settings["silent_mode"] == "1" else "1"
    await db.set_setting("autobackup_silent_mode", new_val)
    settings["silent_mode"] = new_val
    banner = await db.get_setting("banner_file_id")
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), banner=banner or "")
    await call.answer()


@router.callback_query(F.data == "autobackup_set_token")
async def cb_autobackup_set_token(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AutoBackupTokenState.waiting_token)
    await state.update_data(prompt_msg_id=call.message.message_id, prompt_chat_id=call.message.chat.id)
    banner = await db.get_setting("banner_file_id")
    await show(call, "🤖 <b>Токен бота для бэкапов</b>\n\n"
               "Введите токен бота, через который будут отправляться бэкапы:",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_menu", style="danger")],
               ]), banner=banner or "")
    await call.answer()


@router.message(AutoBackupTokenState.waiting_token)
async def on_autobackup_token(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    token = message.text.strip() if message.text else ""
    await db.set_setting("autobackup_bot_token", token)
    data = await state.get_data()
    await state.clear()
    settings = await _get_autobackup_settings(db)
    text = _autobackup_header(settings)
    kb = autobackup_settings_kb(settings)
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    banner = await db.get_setting("banner_file_id")
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, banner=banner or "")
        return
    await show(message, text, reply_markup=kb, banner=banner or "")


@router.callback_query(F.data == "autobackup_set_chat")
async def cb_autobackup_set_chat(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AutoBackupChatIdState.waiting_chat_id)
    await state.update_data(prompt_msg_id=call.message.message_id, prompt_chat_id=call.message.chat.id)
    banner = await db.get_setting("banner_file_id")
    await show(call, "👤 <b>Получатель бэкапов</b>\n\n"
               "Введите Telegram ID получателя бэкапов:",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_menu", style="danger")],
               ]), banner=banner or "")
    await call.answer()


@router.message(AutoBackupChatIdState.waiting_chat_id)
async def on_autobackup_chat_id(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    chat_id_val = message.text.strip() if message.text else ""
    await db.set_setting("autobackup_chat_id", chat_id_val)
    data = await state.get_data()
    await state.clear()
    settings = await _get_autobackup_settings(db)
    text = _autobackup_header(settings)
    kb = autobackup_settings_kb(settings)
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    banner = await db.get_setting("banner_file_id")
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, banner=banner or "")
        return
    await show(message, text, reply_markup=kb, banner=banner or "")


@router.callback_query(F.data == "autobackup_set_freq")
async def cb_autobackup_set_freq(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    banner = await db.get_setting("banner_file_id")
    await show(call, "🕐 <b>Частота автобэкапа</b>\n\nВыберите периодичность:",
               reply_markup=autobackup_freq_kb(), banner=banner or "")
    await call.answer()


@router.callback_query(F.data.startswith("abfreq:"))
async def cb_autobackup_freq_select(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    freq = call.data.split(":")[1]
    await db.set_setting("autobackup_frequency", freq)
    settings = await _get_autobackup_settings(db)
    banner = await db.get_setting("banner_file_id")
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), banner=banner or "")
    await call.answer()


@router.callback_query(F.data == "autobackup_force")
async def cb_autobackup_force(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    await call.answer("⏳ Отправляем бэкап...")
    if settings["bot_token"] and settings["chat_id"]:
        success = await send_autobackup(db, manual=True)
    else:
        success = await send_autobackup_local(db, call.bot, call.message.chat.id)
    if success:
        note = await call.message.answer("✅ Бэкап отправлен!")
    else:
        note = await call.message.answer("❌ Ошибка отправки бэкапа.")
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
    # Обновляем меню
    settings = await _get_autobackup_settings(db)
    banner = await db.get_setting("banner_file_id")
    try:
        await show(call, _autobackup_header(settings),
                   reply_markup=autobackup_settings_kb(settings), banner=banner or "")
    except Exception:
        pass


# ── Планировщик автобэкапа ────────────────────────────────────────────────────

AUTOBACKUP_THRESHOLDS = {
    "hourly": timedelta(minutes=55),
    "daily": timedelta(hours=23),
    "weekly": timedelta(days=6, hours=23),
    "monthly": timedelta(days=28),
}


async def _should_run_autobackup(db: Database) -> bool:
    settings = await _get_autobackup_settings(db)
    if settings["enabled"] != "1":
        return False
    if not settings["bot_token"] or not settings["chat_id"]:
        return False
    last = settings.get("last_backup_at", "")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    freq = settings.get("frequency", "daily")
    threshold = AUTOBACKUP_THRESHOLDS.get(freq, timedelta(hours=23))
    return (datetime.now(timezone.utc) - dt) >= threshold


async def send_autobackup(db: Database, manual: bool = False) -> bool:
    """Создаёт и отправляет JSON-бэкап через указанный бот + chat_id."""
    import aiohttp
    settings = await _get_autobackup_settings(db)
    bot_token = settings["bot_token"]
    chat_id = settings["chat_id"]

    if not bot_token or not chat_id:
        return False

    backup_data = await db.export_backup()
    raw = json.dumps(backup_data, ensure_ascii=False, indent=2).encode()
    size = len(raw)
    if size < 1024 * 1024:
        size_str = f"{size // 1024}K"
    else:
        size_str = f"{size / 1024 / 1024:.1f}M"

    msk = timezone(timedelta(hours=3))
    date_str = datetime.now(tz=msk).strftime("%d.%m.%Y %H:%M МСК")
    method = "вручную" if manual else "автоматически"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"DFC_License_backup_{ts}.json"

    caption = (
        f"📦 Приложение: DFC License\n"
        f"📁 БД\n"
        f"📏 Размер: {size_str}\n"
        f"📅 {date_str}\n\n"
        f"✅ Бекап создан {method}"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", chat_id)
        form.add_field("caption", caption)
        form.add_field("document", raw, filename=filename, content_type="application/json")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    await db.set_setting("autobackup_last_at", now_iso)
                    return True
                else:
                    return False
    except Exception:
        return False


async def send_autobackup_local(db: Database, bot: Bot, chat_id: int) -> bool:
    """Отправляет бэкап через текущий бот в указанный чат (без внешнего бота)."""
    backup_data = await db.export_backup()
    raw = json.dumps(backup_data, ensure_ascii=False, indent=2).encode()
    size = len(raw)
    if size < 1024 * 1024:
        size_str = f"{size // 1024}K"
    else:
        size_str = f"{size / 1024 / 1024:.1f}M"

    msk = timezone(timedelta(hours=3))
    date_str = datetime.now(tz=msk).strftime("%d.%m.%Y %H:%M МСК")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"DFC_License_backup_{ts}.json"

    caption = (
        f"📦 Приложение: DFC License\n"
        f"📁 БД\n"
        f"📏 Размер: {size_str}\n"
        f"📅 {date_str}\n\n"
        f"✅ Бекап создан вручную"
    )

    try:
        doc = BufferedInputFile(raw, filename=filename)
        await bot.send_document(chat_id, document=doc, caption=caption)
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.set_setting("autobackup_last_at", now_iso)
        return True
    except Exception:
        return False


async def autobackup_loop(db: Database):
    """Фоново проверяет нужно ли делать автобэкап (запускается из main.py)."""
    while True:
        try:
            if await _should_run_autobackup(db):
                await send_autobackup(db, manual=False)
        except Exception:
            pass
        await asyncio.sleep(60)  # Проверяем каждую минуту
