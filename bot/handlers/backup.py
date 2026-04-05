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

MSK = timezone(timedelta(hours=3))


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


def _backup_filename() -> str:
    now = datetime.now(tz=MSK)
    return f"dfc-license_{now.strftime('%d-%m-%y_%H-%M')}.sql.gz"


def _backup_caption(raw: bytes, manual: bool = True) -> str:
    size = len(raw)
    if size < 1024:
        size_str = f"{size}B"
    elif size < 1024 * 1024:
        size_str = f"{size // 1024}K"
    else:
        size_str = f"{size / 1024 / 1024:.1f}M"
    date_str = datetime.now(tz=MSK).strftime("%d.%m.%Y %H:%M МСК")
    method = "вручную" if manual else "автоматически"
    return (
        f"📦 Приложение: DFC License\n"
        f"📁 БД\n"
        f"📏 Размер: {size_str}\n"
        f"📅 {date_str}\n\n"
        f"✅ Бекап создан {method}"
    )


@router.callback_query(F.data == "backup_menu")
async def cb_backup_menu(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await show(call, "💾 <b>Управление БД</b>", reply_markup=backup_kb(), db=db)
    await call.answer()


@router.callback_query(F.data == "backup_save")
async def cb_backup_save(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.answer("⏳ Создаём бэкап...")
    raw = await db.export_sql_gz()
    filename = _backup_filename()
    caption = _backup_caption(raw, manual=True)
    await call.message.answer_document(
        BufferedInputFile(raw, filename=filename),
        caption=caption,
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="backup_load_cancel", style="danger")]
    ])
    await show(call, "📤 Отправьте файл бэкапа (.sql.gz):", reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data == "backup_load_cancel")
async def cb_backup_load_cancel(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    await show(call, "💾 <b>Управление БД</b>", reply_markup=backup_kb(), db=db)
    await call.answer()


@router.message(F.document, F.from_user.func(lambda u: u.id == BOT_ADMIN_ID))
async def backup_load(message: Message, state: FSMContext, db: Database):
    current_state = await state.get_state()
    if current_state != "backup_upload":
        return
    doc: Document = message.document
    fname = doc.file_name or ""
    buf = io.BytesIO()
    await message.bot.download(doc, destination=buf)
    raw = buf.getvalue()
    try:
        if fname.endswith(".sql.gz") or fname.endswith(".gz"):
            await db.import_sql_gz(raw)
        elif fname.endswith(".json"):
            data = json.loads(raw)
            await db.import_backup(data)
        else:
            note = await message.answer("❌ Нужен файл бэкапа (.sql.gz)")
            asyncio.create_task(_auto_delete(message.bot, message.chat.id, note.message_id))
            return
    except Exception as e:
        note = await message.answer(f"❌ Ошибка импорта: {e}")
        asyncio.create_task(_auto_delete(message.bot, message.chat.id, note.message_id))
        return
    await state.clear()
    servers = await db.get_all_servers()
    await show(message, f"✅ Бэкап восстановлен\n\n{clients_header(len(servers))}",
               reply_markup=clients_kb(servers), db=db)


# ── Автобэкап ────────────────────────────────────────────────────────────────

async def _auto_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _notify(call: CallbackQuery, text: str, delay: int = 5, state=None):
    note = await call.message.answer(text)
    asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id, delay))
    if state is not None:
        await state.update_data(_notification_id=note.message_id)
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
    # Сохраняем снимок настроек для отката при нажатии "Отмена"
    await state.update_data(_ab_snapshot={
        "autobackup_enabled": settings["enabled"],
        "autobackup_silent_mode": settings["silent_mode"],
        "autobackup_bot_token": settings["bot_token"],
        "autobackup_chat_id": settings["chat_id"],
        "autobackup_frequency": settings["frequency"],
    })
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), db=db)
    await call.answer()


@router.callback_query(F.data == "_noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "autobackup_cancel")
async def cb_autobackup_cancel(call: CallbackQuery, state: FSMContext, db: Database):
    """Отмена — откат к сохранённому снимку настроек."""
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    snapshot = data.get("_ab_snapshot")
    if snapshot:
        for key, val in snapshot.items():
            await db.set_setting(key, val)
    await state.clear()
    await show(call, "💾 <b>Управление БД</b>", reply_markup=backup_kb(), db=db)
    await call.answer()


@router.callback_query(F.data == "autobackup_accept")
async def cb_autobackup_accept(call: CallbackQuery, state: FSMContext, db: Database):
    """Принять — применить изменения, вернуться в меню БД."""
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.clear()
    await show(call, "💾 <b>Управление БД</b>", reply_markup=backup_kb(), db=db)
    await call.answer()


@router.callback_query(F.data == "autobackup_toggle")
async def cb_autobackup_toggle(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    # Если пытаемся включить — проверяем наличие токена и получателя
    if settings["enabled"] != "1":
        if not settings["bot_token"] or not settings["chat_id"]:
            await _notify(call, "⚠️ Сначала укажите токен бота и ID получателя", state=state)
            return
    new_val = "0" if settings["enabled"] == "1" else "1"
    await db.set_setting("autobackup_enabled", new_val)
    settings["enabled"] = new_val
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), db=db)
    await call.answer()


@router.callback_query(F.data == "autobackup_silent")
async def cb_autobackup_silent(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    new_val = "0" if settings["silent_mode"] == "1" else "1"
    await db.set_setting("autobackup_silent_mode", new_val)
    settings["silent_mode"] = new_val
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), db=db)
    await call.answer()


@router.callback_query(F.data == "autobackup_set_token")
async def cb_autobackup_set_token(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AutoBackupTokenState.waiting_token)
    await state.update_data(prompt_msg_id=call.message.message_id, prompt_chat_id=call.message.chat.id)
    await show(call, "🤖 <b>Токен бота для бэкапов</b>\n\n"
               "Введите токен бота, через который будут отправляться бэкапы:",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_menu", style="danger")],
               ]), db=db)
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
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


@router.callback_query(F.data == "autobackup_set_chat")
async def cb_autobackup_set_chat(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(AutoBackupChatIdState.waiting_chat_id)
    await state.update_data(prompt_msg_id=call.message.message_id, prompt_chat_id=call.message.chat.id)
    await show(call, "👤 <b>Получатель бэкапов</b>\n\n"
               "Введите Telegram ID получателя бэкапов:",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="autobackup_menu", style="danger")],
               ]), db=db)
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
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


@router.callback_query(F.data == "autobackup_set_freq")
async def cb_autobackup_set_freq(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await show(call, "🕐 <b>Частота автобэкапа</b>\n\nВыберите периодичность:",
               reply_markup=autobackup_freq_kb(), db=db)
    await call.answer()


@router.callback_query(F.data.startswith("abfreq:"))
async def cb_autobackup_freq_select(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    freq = call.data.split(":")[1]
    await db.set_setting("autobackup_frequency", freq)
    settings = await _get_autobackup_settings(db)
    await show(call, _autobackup_header(settings),
               reply_markup=autobackup_settings_kb(settings), db=db)
    await call.answer()


@router.callback_query(F.data == "autobackup_force")
async def cb_autobackup_force(call: CallbackQuery, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    settings = await _get_autobackup_settings(db)
    await call.answer()
    # Ручная отправка: всегда отправляем и на configured recipient и в наш чат
    # (тихий режим на ручную отправку не влияет)
    if settings["bot_token"] and settings["chat_id"]:
        await send_autobackup(db, manual=True)
    # Всегда также отправляем в текущий чат бота
    success = await send_autobackup_local(db, call.bot, call.message.chat.id,
                                          update_last_at=not bool(settings["bot_token"] and settings["chat_id"]))
    if not success:
        note = await call.message.answer("❌ Ошибка отправки бэкапа.")
        asyncio.create_task(_auto_delete(call.bot, call.message.chat.id, note.message_id))
    # Обновляем меню
    settings = await _get_autobackup_settings(db)
    try:
        await show(call, _autobackup_header(settings),
                   reply_markup=autobackup_settings_kb(settings), db=db)
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

    freq = settings.get("frequency", "daily")
    now = datetime.now(MSK)
    last = settings.get("last_backup_at", "")

    last_dt_msk = None
    if last:
        try:
            dt = datetime.fromisoformat(last)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            last_dt_msk = dt.astimezone(MSK)
        except (ValueError, TypeError):
            pass

    if freq == "hourly":
        # Запускаем в начале каждого часа (00, 01, 02, ...)
        if now.minute != 0:
            return False
        if last_dt_msk is None:
            return True
        # Не запускать снова в том же часу
        return last_dt_msk.strftime("%Y-%m-%d %H") != now.strftime("%Y-%m-%d %H")
    else:
        # Все остальные варианты (daily, weekly, monthly) — в 15:00 МСК
        if now.hour != 15 or now.minute != 0:
            return False
        if last_dt_msk is None:
            return True
        threshold = AUTOBACKUP_THRESHOLDS.get(freq, timedelta(hours=23))
        return (datetime.now(timezone.utc) - last_dt_msk.astimezone(timezone.utc)) >= threshold


async def send_autobackup(db: Database, manual: bool = False) -> bool:
    """Создаёт и отправляет SQL-бэкап через указанный бот + chat_id."""
    import aiohttp
    settings = await _get_autobackup_settings(db)
    bot_token = settings["bot_token"]
    chat_id = settings["chat_id"]

    if not bot_token or not chat_id:
        return False

    raw = await db.export_sql_gz()
    filename = _backup_filename()
    caption = _backup_caption(raw, manual=manual)

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", chat_id)
        form.add_field("caption", caption)
        form.add_field("document", raw, filename=filename, content_type="application/gzip")

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


async def send_autobackup_local(db: Database, bot: Bot, chat_id: int, update_last_at: bool = True) -> bool:
    """Отправляет бэкап через текущий бот в указанный чат (без внешнего бота)."""
    raw = await db.export_sql_gz()
    filename = _backup_filename()
    caption = _backup_caption(raw, manual=True)

    try:
        doc = BufferedInputFile(raw, filename=filename)
        await bot.send_document(chat_id, document=doc, caption=caption,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="✅ Закрыть", callback_data="close_backup_doc", style="success")],
                                ]))
        if update_last_at:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.set_setting("autobackup_last_at", now_iso)
        return True
    except Exception:
        return False


async def autobackup_loop(db: Database, bot: Bot = None):
    """Фоново проверяет нужно ли делать автобэкап (запускается из main.py)."""
    while True:
        try:
            if await _should_run_autobackup(db):
                settings = await _get_autobackup_settings(db)
                await send_autobackup(db, manual=False)
                # Если тихий режим выключен — также отправляем в чат лиц-бота
                if settings.get("silent_mode") != "1" and bot is not None:
                    await send_autobackup_local(db, bot, BOT_ADMIN_ID, update_last_at=False)
        except Exception:
            pass
        # Спим до начала следующей минуты, чтобы не дрейфовать мимо :00
        _now = datetime.now(MSK)
        _sleep_secs = 60 - _now.second - _now.microsecond / 1_000_000
        await asyncio.sleep(_sleep_secs)
