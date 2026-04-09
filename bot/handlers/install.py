import html as _html

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import LICENSE_SERVER_URL, SITE_URL
from database import Database
from bot.banner import show

router = Router()

INSTALL_COMMAND = f"bash <(curl -sL {LICENSE_SERVER_URL}/api/v1/manager/install)"
_INSTALL_COMMAND_HTML = _html.escape(INSTALL_COMMAND)

_site_line = ""
if SITE_URL:
    _site_line = f'\n\n📖 <a href="{SITE_URL}#install">Подробная инструкция на сайте</a>'

INSTALL_TEXT = (
    "📥 <b>Установка DFC Manager</b>\n\n"
    "DFC Manager — единый установщик для всех наших продуктов:\n\n"
    "🆓 <b>Без лицензии:</b>\n"
    "• Remnawave Panel — VPN панель\n"
    "• Subscribe Page — страница подписки\n"
    "• Remnawave Node — нода\n"
    "• Дополнительные утилиты\n\n"
    "🔑 <b>С лицензией:</b>\n"
    "• Remnasale — бот продажи подписок\n"
    "• DFC Support — бот поддержки\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "📋 <b>Команда для установки:</b>\n\n"
    f"<code>{_INSTALL_COMMAND_HTML}</code>\n\n"
    "💡 Скопируйте команду и вставьте в терминал Ubuntu (22.04 / 24.04)"
    f"{_site_line}"
)


@router.callback_query(F.data == "install_guide")
async def cb_install_guide(call: CallbackQuery, db: Database):
    buttons = []
    if SITE_URL:
        buttons.append([InlineKeyboardButton(text="📖 Сайт DFC Project", url=SITE_URL)])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main", style="primary")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await show(call, INSTALL_TEXT, reply_markup=kb, db=db)
    await call.answer()
