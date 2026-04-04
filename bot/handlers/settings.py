from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from bot.states import (
    SettingsIntervalState, SettingsOfflineGraceState,
    SettingsSupportUrlState, SettingsCommunityUrlState,
)
from bot.keyboards.settings import (
    settings_kb, sync_kb, setting_edit_kb, setting_edit_pending_kb,
)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == BOT_ADMIN_ID


# ── Настройки ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await call.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=settings_kb())
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
        reply_markup=settings_kb(),
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
        reply_markup=settings_kb(),
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
        reply_markup=settings_kb(),
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
        reply_markup=settings_kb(),
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
