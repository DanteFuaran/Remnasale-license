"""Middleware для автоматического удаления уведомлений при нажатии любой кнопки."""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery


class ClearNotificationMiddleware(BaseMiddleware):
    """Удаляет авто-удаляемые уведомления при нажатии любой кнопки."""

    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state:
            fsm_data = await state.get_data()
            bot = event.bot
            chat_id = event.message.chat.id if event.message else None
            if chat_id:
                for key in ("_notification_id", "_key_note_id"):
                    msg_id = fsm_data.get(key)
                    if msg_id:
                        try:
                            await bot.delete_message(chat_id, msg_id)
                        except Exception:
                            pass
                if fsm_data.get("_notification_id") or fsm_data.get("_key_note_id"):
                    await state.update_data(_notification_id=None, _key_note_id=None)
        return await handler(event, data)
