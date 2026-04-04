from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

router = Router()


@router.message()
async def auto_delete_unrelated(message: Message, state: FSMContext):
    """Удаляет любое сообщение, не обработанное другими хендлерами."""
    try:
        await message.delete()
    except Exception:
        pass
