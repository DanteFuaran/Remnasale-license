import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BufferedInputFile

from config import BOT_TOKEN, API_HOST, API_PORT, DATABASE_PATH, BOT_ADMIN_ID
from database import LicenseDB
from api import setup_routes
from bot.handlers import setup_routers
from bot.handlers.backup import autobackup_loop
from bot.middleware import ClearNotificationMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_BANNER_PATH = os.path.join(os.path.dirname(__file__), "default_banner.jpg")


async def _init_default_banner(bot: Bot, db: LicenseDB):
    """Если баннер ещё не задан — загружаем дефолтный из файла."""
    existing = await db.get_setting("banner_file_id")
    if existing:
        return
    if not os.path.exists(_DEFAULT_BANNER_PATH):
        return
    if not BOT_ADMIN_ID:
        return
    try:
        with open(_DEFAULT_BANNER_PATH, "rb") as f:
            photo = BufferedInputFile(f.read(), filename="banner.jpg")
        msg = await bot.send_photo(BOT_ADMIN_ID, photo=photo,
                                   caption="🖼 Баннер по умолчанию установлен автоматически.")
        file_id = msg.photo[-1].file_id
        await db.set_setting("banner_file_id", file_id)
        await bot.delete_message(BOT_ADMIN_ID, msg.message_id)
        logger.info("[banner] Default banner initialized")
    except Exception as e:
        logger.warning(f"[banner] Failed to init default banner: {e}")


async def main():
    db = LicenseDB(DATABASE_PATH)
    await db.init()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.set_my_commands([BotCommand(command="start", description="Главное меню")])

    await _init_default_banner(bot, db)

    dp = Dispatcher()
    dp["db"] = db
    dp.callback_query.middleware(ClearNotificationMiddleware())
    setup_routers(dp)

    app = web.Application()
    app["db"] = db
    app["bot"] = bot
    setup_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, API_HOST, API_PORT)
    await site.start()
    logger.info(f"API server started on {API_HOST}:{API_PORT}")

    asyncio.create_task(autobackup_loop(db, bot))
    logger.info("Autobackup scheduler started")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
