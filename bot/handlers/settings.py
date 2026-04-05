import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from bot.banner import show
from bot.states import (
    SettingsIntervalState, SettingsOfflineGraceState,
    SettingsSupportUrlState, SettingsCommunityUrlState,
    BrandingBannerState,
)
from bot.keyboards.settings import (
    settings_kb, sync_kb, setting_edit_kb, setting_edit_pending_kb, branding_kb,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


def _settings_header() -> str:
    try:
        with open("/app/version") as f:
            for line in f:
                if line.startswith("version:"):
                    ver = line.split(":", 1)[1].strip()
                    return f"DFC License server: Версия {ver}\n\n⚙️ <b>Настройки</b>"
    except Exception:
        pass
    return "⚙️ <b>Настройки</b>"


# ── Настройки ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await show(call, _settings_header(), reply_markup=settings_kb(), db=db)
    await call.answer()


# ── Настройка синхронизации ────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_sync")
async def cb_settings_sync(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    await show(call, "🔄 <b>Настройка синхронизации</b>",
               reply_markup=sync_kb(interval, grace), db=db)
    await call.answer()


# ── Интервал проверки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_check_interval")
async def cb_settings_interval(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsIntervalState.waiting_interval)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await show(call, "🔄 Введите интервал проверки в <b>минутах</b> (1–1440):",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_sync", style="danger")],
               ]), db=db)
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
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


# ── Офлайн-период ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_offline_grace")
async def cb_settings_offline_grace(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsOfflineGraceState.waiting_days)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await show(call, "📡 Введите количество <b>дней</b> автономной работы (1–365):",
               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                   [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_sync", style="danger")],
               ]), db=db)
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
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


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
    await show(call, _support_edit_text(current),
               reply_markup=setting_edit_kb("clear_support", "settings_menu"), db=db)
    await call.answer()
async def cb_clear_support(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("support_url", "")
    await state.clear()
    await show(call, f"✅ Поддержка очищена\n\n{_settings_header()}",
               reply_markup=settings_kb(), db=db)
    await call.answer()


@router.callback_query(F.data == "accept_support")
async def cb_accept_support(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    val = data.get("pending_value") or ""
    await db.set_setting("support_url", val)
    await state.clear()
    await show(call, f"✅ Поддержка: <b>{val}</b>\n\n{_settings_header()}",
               reply_markup=settings_kb(), db=db)
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
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


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
    await show(call, _community_edit_text(current),
               reply_markup=setting_edit_kb("clear_community", "settings_menu"), db=db)
    await call.answer()


@router.callback_query(F.data == "clear_community")
async def cb_clear_community(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("community_url", "")
    await state.clear()
    await show(call, f"✅ Сообщество очищено\n\n{_settings_header()}",
               reply_markup=settings_kb(), db=db)
    await call.answer()


@router.callback_query(F.data == "accept_community")
async def cb_accept_community(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    data = await state.get_data()
    val = data.get("pending_value") or ""
    await db.set_setting("community_url", val)
    await state.clear()
    await show(call, f"✅ Сообщество: <b>{val}</b>\n\n{_settings_header()}",
               reply_markup=settings_kb(), db=db)
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
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


# ── Брендирование ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _auto_delete_s(bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


@router.callback_query(F.data == "branding_menu")
async def cb_branding_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    banner = await db.get_setting("banner_file_id") or ""
    kb = branding_kb(has_banner=bool(banner))
    text = "🎨 <b>Брендирование</b>\n\nВыберите нужный пункт"
    await show(call, text, reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data == "branding_change_banner")
async def cb_branding_change_banner(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(BrandingBannerState.waiting_photo)
    await state.update_data(
        prompt_msg_id=call.message.message_id,
        prompt_chat_id=call.message.chat.id,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="branding_menu", style="danger")],
    ])
    await show(call, "🖼 <b>Загрузка банера</b>\n\n"
               "Отправьте изображение (JPG или PNG), которое станет банером.",
               reply_markup=kb, db=db)
    await call.answer()


@router.message(BrandingBannerState.waiting_photo)
async def on_banner_photo(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.photo:
        note = await message.answer("⚠️ Необходимо отправить фото (JPG или PNG).")
        asyncio.create_task(_auto_delete_s(message.bot, message.chat.id, note.message_id))
        return
    file_id = message.photo[-1].file_id
    await db.set_setting("banner_file_id", file_id)
    data = await state.get_data()
    await state.clear()
    note = await message.answer("✅ Банер успешно установлен!")
    asyncio.create_task(_auto_delete_s(message.bot, message.chat.id, note.message_id))
    await state.update_data(_notification_id=note.message_id)
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    kb = branding_kb(has_banner=True)
    text = "🎨 <b>Брендирование</b>\n\nВыберите нужный пункт"
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, banner=file_id)
        return
    await show(message, text, reply_markup=kb, banner=file_id)
