import asyncio
import logging
import os
from datetime import datetime, timezone
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, API_HOST, API_PORT, DATABASE_PATH, BOT_ADMIN_ID, TELEGRAM_PROXY
from database import LicenseDB
from api import setup_routes, push_license_event
from bot.handlers import setup_routers
from bot.handlers.backup import autobackup_loop
from bot.middleware import ClearNotificationMiddleware
from github_sync import github_sync_loop

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
    """Фоновый мониторинг: если клиент молчит дольше 3 * check_interval — уведомляем.
    Если молчит дольше silence_suspend_days — автоматически приостанавливаем лицензию.
    """
    await asyncio.sleep(60)  # Дать серверу запуститься
    while True:
        try:
            check_interval = await db.get_check_interval()
            # Порог: равен интервалу проверки (1 пропущенная проверка)
            threshold = check_interval
            silent = await db.get_silent_servers(threshold)

            silent_ids = {s["id"] for s in silent}
            notified_silent = await _load_silent(db)

            # ── Авто-приостановка при длительном молчании ────────────
            suspend_days = await db.get_silence_suspend_days()
            if suspend_days > 0:
                suspend_threshold_min = suspend_days * 1440
                to_suspend = await db.get_servers_for_auto_suspend(suspend_threshold_min)
                for s in to_suspend:
                    sid = s["id"]
                    # Перечитываем свежие данные — сервер мог ожить
                    _fresh = await db.get_server(sid)
                    if not _fresh or not _fresh.get("is_active") or _fresh.get("is_blacklisted"):
                        continue
                    # Приостанавливаем
                    await db.set_server_active(sid, 0)
                    # Запоминаем причину авто-приостановки
                    await db.set_setting(f"auto_suspended:{sid}", "silence")
                    asyncio.create_task(push_license_event(db, sid, "suspended"))
                    logger.warning(
                        f"[monitor] Auto-suspended server {_fresh['name']} (id={sid}): "
                        f"silent for >{suspend_days} days"
                    )
                    if BOT_ADMIN_ID:
                        text = (
                            f"⛔ <b>Авто-приостановка!</b>\n\n"
                            f"Сервер: <b>{_fresh['name']}</b>\n"
                            f"IP: <code>{_fresh.get('server_ip', '—')}</code>\n\n"
                            f"Причина: нет связи более <b>{suspend_days} дн.</b>\n"
                            f"Лицензия приостановлена автоматически."
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(
                                text="▶️ Возобновить",
                                callback_data=f"tgl:{sid}",
                            )],
                            [InlineKeyboardButton(
                                text="❌ Закрыть",
                                callback_data="dismiss_notify_offline",
                                style="danger",
                            )],
                        ])
                        try:
                            await bot.send_message(BOT_ADMIN_ID, text, reply_markup=kb)
                        except Exception:
                            pass
                    # Убираем из silent-трекинга (уже приостановлен)
                    notified_silent.discard(sid)
                    silent_ids.discard(sid)

            # Восстановившиеся серверы
            recovered = notified_silent - silent_ids
            truly_recovered = set()
            for sid in recovered:
                server = await db.get_server(sid)
                if not server:
                    notified_silent.discard(sid)
                    continue
                # Проверяем что last_check_at действительно свежий (сервер реально ожил)
                last_check = server.get("last_check_at")
                if not last_check:
                    # last_check_at нет — сервер не чекинился, просто убираем из notified без алерта
                    notified_silent.discard(sid)
                    continue
                try:
                    dt = datetime.fromisoformat(last_check)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - dt).total_seconds() / 60
                except (ValueError, TypeError):
                    notified_silent.discard(sid)
                    continue
                if elapsed >= check_interval:
                    # last_check_at всё ещё старый — сервер на самом деле не ожил,
                    # просто выпал из мониторинга по другой причине (напр. IP сброшен).
                    # Убираем без алерта.
                    notified_silent.discard(sid)
                    continue
                truly_recovered.add(sid)
                if BOT_ADMIN_ID:
                    _domain = (server.get('app_domain') or '').strip()
                    _domain_line = f"\n🌐 Домен: <code>{_domain}</code>" if _domain else ""
                    text = (
                        f"🟢 <b>Связь восстановлена!</b>\n\n"
                        f"Сервер: <b>{server['name']}</b>\n"
                        f"IP: <code>{server.get('server_ip', '—')}</code>"
                        f"{_domain_line}"
                    )
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_notify_offline")],
                    ])
                    try:
                        await bot.send_message(BOT_ADMIN_ID, text, reply_markup=kb, parse_mode="HTML")
                    except Exception:
                        pass
            notified_silent.difference_update(truly_recovered)

            # Новые молчащие серверы
            for s in silent:
                if s["id"] in notified_silent:
                    continue
                if s.get("is_muted"):
                    continue
                # Свежая проверка: сервер мог быть приостановлен/заблокирован
                # после того как get_silent_servers прочитала данные (race condition)
                _fresh = await db.get_server(s["id"])
                if not _fresh or not _fresh.get("is_active") or _fresh.get("is_blacklisted"):
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

    bot_kwargs = {"token": BOT_TOKEN, "default": DefaultBotProperties(parse_mode="HTML")}
    if TELEGRAM_PROXY:
        from aiogram.client.session.aiohttp import AiohttpSession
        bot_kwargs["session"] = AiohttpSession(proxy=TELEGRAM_PROXY)
    bot = Bot(**bot_kwargs)
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Главное меню")])
    except Exception as e:
        logger.warning(f"Failed to set bot commands (Telegram unreachable?): {e}")

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

    asyncio.create_task(github_sync_loop())
    logger.info("GitHub sync started")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
