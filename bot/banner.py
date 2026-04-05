"""Утилита для отображения меню с баннером."""
from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)


async def show(
    target: CallbackQuery | Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    banner: str = "",
    db=None,  # Database | None — если передан и banner пустой, загружает banner_file_id автоматически
) -> Message:
    """Показать меню с опциональным баннером.

    target — CallbackQuery (edit) или Message (send).
    banner — file_id изображения (пустая строка = без баннера).
    db — если передан и banner пустой, автоматически загружает banner_file_id из настроек.
    Возвращает объект отправленного/отредактированного сообщения.
    """
    if not banner and db is not None:
        banner = await db.get_setting("banner_file_id") or ""
    if isinstance(target, CallbackQuery):
        msg = target.message
        # Если баннер не задан явно/через db, но текущее сообщение уже фото —
        # берём его file_id чтобы не потерять баннер при навигации
        if not banner and msg.photo:
            banner = msg.photo[-1].file_id
        if banner:
            try:
                media = InputMediaPhoto(media=banner, caption=text, parse_mode="HTML")
                await msg.edit_media(media=media, reply_markup=reply_markup)
                return msg
            except Exception:
                pass
            # Не удалось отредактировать — удаляем и отправляем новое
            try:
                await msg.delete()
            except Exception:
                pass
            return await msg.answer_photo(
                photo=banner, caption=text, reply_markup=reply_markup,
            )
        else:
            try:
                await msg.edit_text(text, reply_markup=reply_markup)
                return msg
            except Exception:
                pass
            try:
                await msg.delete()
            except Exception:
                pass
            return await msg.answer(text, reply_markup=reply_markup)
    else:
        # Message (например после /start или ввода текста)
        if banner:
            return await target.answer_photo(
                photo=banner, caption=text, reply_markup=reply_markup,
            )
        else:
            return await target.answer(text, reply_markup=reply_markup)


async def edit_prompt(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    banner: str = "",
    db=None,  # Database | None
) -> int:
    """Редактирует ранее отправленное сообщение (prompt_msg_id) с учётом баннера.

    Возвращает message_id итогового сообщения.
    """
    if not banner and db is not None:
        banner = await db.get_setting("banner_file_id") or ""
    if banner:
        try:
            media = InputMediaPhoto(media=banner, caption=text, parse_mode="HTML")
            await bot.edit_message_media(
                media=media, chat_id=chat_id,
                message_id=message_id, reply_markup=reply_markup,
            )
            return message_id
        except Exception:
            pass
    else:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id,
                reply_markup=reply_markup, parse_mode="HTML",
            )
            return message_id
        except Exception:
            pass
    # Fallback: удалить старое, отправить новое
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass
    if banner:
        m = await bot.send_photo(
            chat_id, photo=banner, caption=text, reply_markup=reply_markup,
        )
    else:
        m = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    return m.message_id
