import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_ADMIN_ID
from database import Database
from bot.banner import show
from bot.states import (
    SettingsIntervalState, SettingsOfflineGraceState, SettingsSilenceSuspendState,
    SettingsSupportUrlState, SettingsCommunityUrlState,
    BrandingBannerState, SettingsLicenseHostState,
    DonateMessageState, DonateBtnLabelState, DonateBtnUrlState,
)
from bot.keyboards.settings import (
    settings_kb, sync_kb, setting_edit_kb, setting_edit_pending_kb, branding_kb,
    donate_kb, donate_btn_kb,
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
    suspend = await db.get_silence_suspend_days()
    await show(call, "🔄 <b>Настройка синхронизации</b>",
               reply_markup=sync_kb(interval, grace, suspend), db=db)
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
    suspend = await db.get_silence_suspend_days()
    text = f"✅ Интервал: <b>{val} мин.</b>\n\n🔄 <b>Настройка синхронизации</b>"
    kb = sync_kb(interval, grace, suspend)
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
    suspend = await db.get_silence_suspend_days()
    text = f"✅ Автономность: <b>{val} дн.</b>\n\n🔄 <b>Настройка синхронизации</b>"
    kb = sync_kb(interval, grace, suspend)
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text, reply_markup=kb, db=db)
        return
    await show(message, text, reply_markup=kb, db=db)


# ── Авто-приостановка при молчании ─────────────────────────────────────────────

@router.callback_query(F.data == "settings_silence_suspend")
async def cb_settings_silence_suspend(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await state.set_state(SettingsSilenceSuspendState.waiting_days)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    await show(call, (
        "⛔ Введите через сколько <b>дней</b> молчания "
        "автоматически приостановить лицензию (0 = откл., 1–365):\n\n"
        "<i>Если клиент не отправляет запросы проверки "
        "дольше указанного срока, лицензия будет "
        "приостановлена автоматически.</i>"
    ), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_sync", style="danger")],
    ]), db=db)
    await call.answer()


@router.message(SettingsSilenceSuspendState.waiting_days)
async def on_silence_suspend_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    try:
        val = int(message.text.strip())
        if not 0 <= val <= 365:
            raise ValueError
    except ValueError:
        return
    await db.set_silence_suspend_days(val)
    data = await state.get_data()
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    interval = await db.get_check_interval()
    grace = await db.get_offline_grace_days()
    suspend = await db.get_silence_suspend_days()
    label = f"{val} дн." if val > 0 else "Откл."
    text = f"✅ Авто-приостановка: <b>{label}</b>\n\n🔄 <b>Настройка синхронизации</b>"
    kb = sync_kb(interval, grace, suspend)
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


# ── Домен лиц. сервера ─────────────────────────────────────────────────────────

def _license_host_text(current: str) -> str:
    display = current or "Не указан (используется значение из .env клиентов)"
    return (
        "🌐 <b>Домен лиц. сервера</b>\n\n"
        f"<blockquote>🌐 Текущий домен: {display}</blockquote>\n\n"
        "ℹ️ <i>Введите новый домен (например <b>https://license.dfc-online.com</b>).\n"
        "Клиентские боты получат его при следующей проверке лицензии и автоматически обновятся.</i>"
    )


@router.callback_query(F.data == "settings_license_host")
async def cb_settings_license_host(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = await db.get_setting("license_host")
    await state.set_state(SettingsLicenseHostState.waiting_host)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    kb = setting_edit_kb("clear_license_host", "settings_menu")
    await show(call, _license_host_text(current), reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data == "clear_license_host")
async def cb_clear_license_host(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("license_host", "")
    await state.clear()
    await show(call, f"✅ Домен лиц. сервера очищен\n\n{_settings_header()}",
               reply_markup=settings_kb(), db=db)
    await call.answer()


@router.message(SettingsLicenseHostState.waiting_host)
async def on_license_host_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    raw = message.text.strip().rstrip("/")
    if not raw.startswith("http"):
        raw = "https://" + raw
    await db.set_setting("license_host", raw)
    await state.clear()
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    text = f"✅ Домен лиц. сервера обновлён: <b>{raw}</b>\n\n{_settings_header()}"
    if prompt_msg_id:
        from bot.banner import edit_prompt
        await edit_prompt(message.bot, chat_id, prompt_msg_id, text,
                          reply_markup=settings_kb(), db=db)
    else:
        await show(message, text, reply_markup=settings_kb(), db=db)


# ── Брендирование ─────────────────────────────────────────────────────────────

async def _auto_delete_s(bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _auto_delete_s(bot, chat_id: int, message_id: int, delay: int = 5):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ── Донаты ─────────────────────────────────────────────────────────────────────

async def _get_donate_btn(db: Database, idx: int) -> dict:
    return {
        "enabled": (await db.get_setting(f"donate_btn{idx}_enabled")) == "1",
        "label": await db.get_setting(f"donate_btn{idx}_label"),
        "url": await db.get_setting(f"donate_btn{idx}_url"),
    }


async def _donate_menu(target, state: FSMContext, db: Database):
    await state.clear()
    enabled = (await db.get_setting("donate_enabled")) == "1"
    btn1 = await _get_donate_btn(db, 1)
    btn2 = await _get_donate_btn(db, 2)
    btn3 = await _get_donate_btn(db, 3)
    msg = await db.get_setting("donate_message")
    msg_preview = (msg[:80] + "…") if msg and len(msg) > 80 else (msg or "Не задано")
    text = (
        f"💝 <b>Настройка донатов</b>\n\n"
        f"Сообщение: {msg_preview}"
    )
    await show(target, text, reply_markup=donate_kb(enabled, btn1, btn2, btn3), db=db)


@router.callback_query(F.data == "settings_donate")
async def cb_settings_donate(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await _donate_menu(call, state, db)
    await call.answer()


@router.callback_query(F.data == "donate_toggle")
async def cb_donate_toggle(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = (await db.get_setting("donate_enabled")) == "1"
    await db.set_setting("donate_enabled", "0" if current else "1")
    await _donate_menu(call, state, db)
    await call.answer()


@router.callback_query(F.data == "donate_edit_message")
async def cb_donate_edit_message(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    current = await db.get_setting("donate_message")
    preview = current or "<i>не задано</i>"
    await state.set_state(DonateMessageState.waiting_text)
    await state.update_data(prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    text = (
        "📝 <b>Настройка сообщения донатов</b>\n\n"
        f"<blockquote>{preview}</blockquote>\n\n"
        "ℹ️ <i>Отправьте новый текст сообщения. Поддерживается HTML-разметка.</i>"
    )
    kb = setting_edit_kb("donate_clear_message", "settings_donate")
    await show(call, text, reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data == "donate_clear_message")
async def cb_donate_clear_message(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    await db.set_setting("donate_message", "")
    await state.clear()
    await _donate_menu(call, state, db)
    await call.answer()


@router.message(DonateMessageState.waiting_text)
async def on_donate_message_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    text = message.text or message.caption or ""
    await db.set_setting("donate_message", text.strip())
    data = await state.get_data()
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    if prompt_msg_id:
        from bot.banner import edit_prompt
        enabled = (await db.get_setting("donate_enabled")) == "1"
        btn1 = await _get_donate_btn(db, 1)
        btn2 = await _get_donate_btn(db, 2)
        btn3 = await _get_donate_btn(db, 3)
        msg = await db.get_setting("donate_message")
        msg_preview = (msg[:80] + "…") if msg and len(msg) > 80 else (msg or "Не задано")
        await edit_prompt(message.bot, chat_id, prompt_msg_id,
                          f"💝 <b>Настройка донатов</b>\n\nСообщение: {msg_preview}",
                          reply_markup=donate_kb(enabled, btn1, btn2, btn3), db=db)
    else:
        note = await message.answer("✅ Сообщение обновлено")
        asyncio.create_task(_auto_delete_s(message.bot, message.chat.id, note.message_id))


# ── Кнопки донатов ─────────────────────────────────────────────────────────────

async def _show_donate_btn(target, state: FSMContext, db: Database, idx: int):
    await state.clear()
    btn = await _get_donate_btn(db, idx)
    label = btn.get("label") or "Не задано"
    url = btn.get("url") or "Не задана"
    text = (
        f"🔘 <b>Кнопка {idx}</b>\n\n"
        f"Название: {label}\n"
        f"Ссылка: {url}"
    )
    await show(target, text, reply_markup=donate_btn_kb(idx, btn), db=db)


@router.callback_query(F.data.in_({"donate_btn_1", "donate_btn_2", "donate_btn_3"}))
async def cb_donate_btn(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data[-1])
    await _show_donate_btn(call, state, db, idx)
    await call.answer()


@router.callback_query(F.data.in_({"donate_btn_1_toggle", "donate_btn_2_toggle", "donate_btn_3_toggle"}))
async def cb_donate_btn_toggle(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data.split("_")[2])
    key = f"donate_btn{idx}_enabled"
    current = (await db.get_setting(key)) == "1"
    await db.set_setting(key, "0" if current else "1")
    await _show_donate_btn(call, state, db, idx)
    await call.answer()


@router.callback_query(F.data.in_({"donate_btn_1_label", "donate_btn_2_label", "donate_btn_3_label"}))
async def cb_donate_btn_label(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data.split("_")[2])
    await state.set_state(DonateBtnLabelState.waiting_label)
    await state.update_data(btn_idx=idx, prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    current = await db.get_setting(f"donate_btn{idx}_label")
    text = (
        f"✏️ <b>Название кнопки {idx}</b>\n\n"
        f"Текущее: {current or '<i>не задано</i>'}\n\n"
        "ℹ️ <i>Введите новое название кнопки.</i>"
    )
    kb = setting_edit_kb(f"donate_btn_{idx}_clear_label", f"donate_btn_{idx}")
    await show(call, text, reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data.in_({"donate_btn_1_clear_label", "donate_btn_2_clear_label", "donate_btn_3_clear_label"}))
async def cb_donate_btn_clear_label(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data.split("_")[2])
    await db.set_setting(f"donate_btn{idx}_label", "")
    await state.clear()
    await _show_donate_btn(call, state, db, idx)
    await call.answer()


@router.message(DonateBtnLabelState.waiting_label)
async def on_donate_btn_label_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    idx = data.get("btn_idx", 1)
    await db.set_setting(f"donate_btn{idx}_label", message.text.strip())
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    if prompt_msg_id:
        from bot.banner import edit_prompt
        btn = await _get_donate_btn(db, idx)
        label = btn.get("label") or "Не задано"
        url = btn.get("url") or "Не задана"
        await edit_prompt(message.bot, chat_id, prompt_msg_id,
                          f"🔘 <b>Кнопка {idx}</b>\n\nНазвание: {label}\nСсылка: {url}",
                          reply_markup=donate_btn_kb(idx, btn), db=db)
    else:
        note = await message.answer("✅ Название обновлено")
        asyncio.create_task(_auto_delete_s(message.bot, message.chat.id, note.message_id))


@router.callback_query(F.data.in_({"donate_btn_1_url", "donate_btn_2_url", "donate_btn_3_url"}))
async def cb_donate_btn_url(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data.split("_")[2])
    await state.set_state(DonateBtnUrlState.waiting_url)
    await state.update_data(btn_idx=idx, prompt_msg_id=call.message.message_id,
                            prompt_chat_id=call.message.chat.id)
    current = await db.get_setting(f"donate_btn{idx}_url")
    text = (
        f"🔗 <b>Ссылка кнопки {idx}</b>\n\n"
        f"Текущая: {current or '<i>не задана</i>'}\n\n"
        "ℹ️ <i>Введите URL ссылки для кнопки.</i>"
    )
    kb = setting_edit_kb(f"donate_btn_{idx}_clear_url", f"donate_btn_{idx}")
    await show(call, text, reply_markup=kb, db=db)
    await call.answer()


@router.callback_query(F.data.in_({"donate_btn_1_clear_url", "donate_btn_2_clear_url", "donate_btn_3_clear_url"}))
async def cb_donate_btn_clear_url(call: CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(call.from_user.id):
        return await call.answer("⛔")
    idx = int(call.data.split("_")[2])
    await db.set_setting(f"donate_btn{idx}_url", "")
    await state.clear()
    await _show_donate_btn(call, state, db, idx)
    await call.answer()


@router.message(DonateBtnUrlState.waiting_url)
async def on_donate_btn_url_input(message: Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    idx = data.get("btn_idx", 1)
    raw = message.text.strip()
    if not raw.startswith("http"):
        raw = "https://" + raw
    await db.set_setting(f"donate_btn{idx}_url", raw)
    await state.clear()
    prompt_msg_id = data.get("prompt_msg_id")
    chat_id = data.get("prompt_chat_id") or message.chat.id
    if prompt_msg_id:
        from bot.banner import edit_prompt
        btn = await _get_donate_btn(db, idx)
        label = btn.get("label") or "Не задано"
        url_val = btn.get("url") or "Не задана"
        await edit_prompt(message.bot, chat_id, prompt_msg_id,
                          f"🔘 <b>Кнопка {idx}</b>\n\nНазвание: {label}\nСсылка: {url_val}",
                          reply_markup=donate_btn_kb(idx, btn), db=db)
    else:
        note = await message.answer("✅ Ссылка обновлена")
        asyncio.create_task(_auto_delete_s(message.bot, message.chat.id, note.message_id))


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
