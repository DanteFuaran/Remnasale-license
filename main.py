import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

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


# Ключ в settings для хранения множества id серверов без связи
_SETTING_SILENT = "monitor_silent_ids"


async def _load_silent(db: LicenseDB) -> set[int]:
    val = await db.get_setting(_SETTING_SILENT, "")
    if not val:
        return set()
    try:
        import json as _json
        return set(int(x) for x in _json.loads(val))
    except Exception:
        return set()


async def _save_silent(db: LicenseDB, ids: set[int]) -> None:
    import json as _json
    await db.set_setting(_SETTING_SILENT, _json.dumps(list(ids)))


async def _monitor_clients_loop(db: LicenseDB, bot: Bot):
    """Фоновый мониторинг: если клиент молчит дольше 3 * check_interval — уведомляем."""
    await asyncio.sleep(60)  # Дать серверу запуститься
    while True:
        try:
            check_interval = await db.get_check_interval()
            # Порог: равен интервалу проверки (1 пропущенная проверка)
            threshold = check_interval
            silent = await db.get_silent_servers(threshold)

            silent_ids = {s["id"] for s in silent}
            notified_silent = await _load_silent(db)

            # Восстановившиеся серверы
            recovered = notified_silent - silent_ids
            for sid in recovered:
                server = await db.get_server(sid)
                if server and BOT_ADMIN_ID:
                    text = (
                        f"🟢 <b>Связь восстановлена!</b>\n\n"
                        f"Сервер: <b>{server['name']}</b>\n"
                        f"IP: <code>{server.get('server_ip', '—')}</code>"
                    )
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_notify_offline", style="success")],
                    ])
                    try:
                        await bot.send_message(BOT_ADMIN_ID, text, reply_markup=kb)
                    except Exception:
                        pass
            notified_silent.difference_update(recovered)

            # Новые молчащие серверы
            for s in silent:
                if s["id"] in notified_silent:
                    continue
                if s.get("is_muted"):
                    continue
                if BOT_ADMIN_ID:
                    text = (
                        f"🔴 <b>Связь потеряна!</b>\n\n"
                        f"Сервер: <b>{s['name']}</b>\n"
                        f"IP: <code>{s.get('server_ip', '—')}</code>"
                    )
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Закрыть", callback_data="dismiss_notify_offline", style="danger")],
                    ])
                    try:
                        await bot.send_message(BOT_ADMIN_ID, text, reply_markup=kb)
                        notified_silent.add(s["id"])
                    except Exception:
                        pass

            await _save_silent(db, notified_silent)

        except Exception as e:
            logger.warning(f"[monitor] Client monitor error: {e}")

        await asyncio.sleep(60)  # Проверять раз в минуту


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

    asyncio.create_task(_monitor_clients_loop(db, bot))
    logger.info("Client monitor started")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
