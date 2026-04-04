import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from config import BOT_TOKEN, API_HOST, API_PORT, DATABASE_PATH
from database import LicenseDB
from api import setup_routes
from bot.handlers import setup_routers
from bot.handlers.backup import autobackup_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    db = LicenseDB(DATABASE_PATH)
    await db.init()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.set_my_commands([BotCommand(command="start", description="Главное меню")])
    dp = Dispatcher()
    dp["db"] = db
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

    asyncio.create_task(autobackup_loop(db))
    logger.info("Autobackup scheduler started")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
