import hashlib
import json
import logging
import os
import time
from aiohttp import web, ClientSession, ClientTimeout
from config import GITHUB_PAT, GITHUB_REPO, BOT_ADMIN_ID

logger = logging.getLogger(__name__)

# ── Cached GitHub version ─────────────────────────────────────────────
_CACHE_TTL = 300  # 5 minutes
_cached_version: str | None = None
_cached_at: float = 0.0
_GITHUB_BRANCH = "lic"


async def _fetch_github_version() -> str:
    """Fetch the 'version' file from the GitHub repo and parse the version string."""
    global _cached_version, _cached_at

    now = time.monotonic()
    if _cached_version and (now - _cached_at) < _CACHE_TTL:
        return _cached_version

    if not GITHUB_PAT or not GITHUB_REPO:
        logger.warning("[version] GITHUB_PAT or GITHUB_REPO not configured")
        return _cached_version or "unknown"

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{_GITHUB_BRANCH}/version"
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3.raw",
    }

    try:
        timeout = ClientTimeout(total=15)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"[version] GitHub returned {resp.status}")
                    return _cached_version or "unknown"
                text = await resp.text()
                for line in text.splitlines():
                    if line.startswith("version:"):
                        version = line.split(":", 1)[1].strip()
                        _cached_version = version
                        _cached_at = now
                        return version
    except Exception as e:
        logger.warning(f"[version] Failed to fetch from GitHub: {e}")

    return _cached_version or "unknown"


async def handle_verify(request: web.Request) -> web.Response:
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"valid": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    server_ip = data.get("server_ip", "").strip()

    if not license_key:
        return web.json_response({"valid": False, "reason": "missing_key"}, status=400)

    result = await db.verify_license(license_key, server_ip)

    check_interval = await db.get_check_interval()
    result["check_interval"] = check_interval

    status = 200 if result["valid"] else 403
    return web.json_response(result, status=status)


async def handle_version(request: web.Request) -> web.Response:
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    version = await _fetch_github_version()
    return web.json_response({"version": version})


async def handle_release(request: web.Request) -> web.Response:
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    server_ip = data.get("server_ip", "").strip()

    if not license_key or not server_ip:
        return web.json_response({"success": False, "reason": "missing_fields"}, status=400)

    result = await db.reset_ip_by_key(license_key, server_ip)
    status = 200 if result["success"] else 403
    return web.json_response(result, status=status)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def handle_download(request: web.Request) -> web.Response:
    """Proxy GitHub tarball download so clients don't need a GitHub PAT."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    if not GITHUB_PAT or not GITHUB_REPO:
        return web.json_response({"error": "download not configured"}, status=503)

    url = f"https://api.github.com/repos/{GITHUB_REPO}/tarball/{_GITHUB_BRANCH}"
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        timeout = ClientTimeout(total=180)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as upstream:
                if upstream.status != 200:
                    return web.Response(status=502, text="Failed to fetch from upstream")

                resp = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "application/gzip",
                        "Content-Disposition": "attachment; filename=remnasale.tar.gz",
                    },
                )
                await resp.prepare(request)
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
    except Exception as e:
        logger.error(f"[download] Proxy error: {e}")
        return web.Response(status=502, text="Download proxy error")


async def handle_install_script(request: web.Request) -> web.Response:
    """Serve the install script from GitHub so clients don't need a PAT."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    if not GITHUB_PAT or not GITHUB_REPO:
        return web.json_response({"error": "not configured"}, status=503)

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{_GITHUB_BRANCH}/remnasale-install.sh"
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3.raw",
    }

    try:
        timeout = ClientTimeout(total=30)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as upstream:
                if upstream.status != 200:
                    logger.warning(f"[install-script] GitHub returned {upstream.status}")
                    return web.Response(status=502, text="Failed to fetch install script")
                script = await upstream.text()
                return web.Response(
                    text=script,
                    content_type="text/plain",
                    headers={"Cache-Control": "no-cache"},
                )
    except Exception as e:
        logger.error(f"[install-script] Error: {e}")
        return web.Response(status=502, text="Failed to fetch install script")


async def handle_notify_offline(request: web.Request) -> web.Response:
    db = request.app["db"]
    bot = request.app.get("bot")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    server_ip = data.get("server_ip", "").strip()
    days_left = int(data.get("days_left", 0))
    event = data.get("event", "offline")

    server = await db.get_server_by_key(license_key)
    server_name = server["name"] if server else (license_key[:16] if license_key else "???")

    if bot and BOT_ADMIN_ID:
        if event == "online":
            text = (
                f"\U0001f7e2 <b>\u0421\u0432\u044f\u0437\u044c \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430</b>\n\n"
                f"\u0421\u0435\u0440\u0432\u0435\u0440: <b>{server_name}</b>\n"
                f"IP: <code>{server_ip}</code>"
            )
        else:
            text = (
                f"\U0001f7e1 <b>\u041a\u043b\u0438\u0435\u043d\u0442 \u043f\u043e\u0442\u0435\u0440\u044f\u043b \u0441\u0432\u044f\u0437\u044c</b>\n\n"
                f"\u0421\u0435\u0440\u0432\u0435\u0440: <b>{server_name}</b>\n"
                f"IP: <code>{server_ip}</code>\n"
                f"\u0410\u0432\u0442\u043e\u043d\u043e\u043c\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430: <b>{days_left} \u0434\u043d.</b>"
            )
        try:
            await bot.send_message(BOT_ADMIN_ID, text)
        except Exception as e:
            logger.warning(f"[notify_offline] Failed to send TG message: {e}")

    return web.json_response({"success": True})


# ── Payment Webhooks ──────────────────────────────────────────────────────

async def _process_paid_order(request: web.Request, order_id: str, payment_data: dict):
    """Обработка оплаченного заказа: создание сервера и уведомление."""
    db = request.app["db"]
    bot = request.app.get("bot")

    order = await db.complete_order(order_id, payment_data)
    if not order:
        return

    server = await db.add_server_for_user(
        user_id=order["user_id"],
        products=order["products"],
        duration=order["duration"],
    )
    key = server["license_key"]

    if bot:
        try:
            text = (
                "✅ <b>Оплата получена!</b>\n\n"
                f"🔑 Ваш лицензионный ключ:\n<code>{key}</code>\n\n"
                f"Используйте этот ключ для установки на вашем сервере."
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main", style="primary")],
            ])
            await bot.send_message(order["user_id"], text, reply_markup=kb)
        except Exception as e:
            logger.warning(f"[webhook] Failed to notify user {order['user_id']}: {e}")

        try:
            product_names = ", ".join(order["products"])
            admin_text = (
                f"🛒 <b>Новая покупка!</b>\n\n"
                f"👤 Пользователь: <code>{order['user_id']}</code>\n"
                f"📦 Продукты: {product_names}\n"
                f"💰 Сумма: {order['amount']} {order['currency']}\n"
                f"🔑 Ключ: <code>{key}</code>"
            )
            await bot.send_message(BOT_ADMIN_ID, admin_text)
        except Exception:
            pass


async def handle_webhook_yoomoney(request: web.Request) -> web.Response:
    """YooMoney webhook: SHA1 verification."""
    db = request.app["db"]

    try:
        data = await request.post()
    except Exception:
        return web.Response(status=400, text="bad request")

    label = data.get("label", "").strip()
    if not label:
        return web.Response(status=400, text="missing label")

    order = await db.get_pending_order(label)
    if not order:
        logger.info(f"[yoomoney] Order not found or already processed: {label}")
        return web.Response(status=200, text="ok")

    # SHA1 verification
    gw = await db.get_gateway("yoomoney")
    if gw:
        secret = (gw.get("settings", {}).get("secret_key", "") or "").strip()
        if secret:
            check_str = "&".join([
                str(data.get("notification_type", "")),
                str(data.get("operation_id", "")),
                str(data.get("amount", "")),
                str(data.get("currency", "")),
                str(data.get("datetime", "")),
                str(data.get("sender", "")),
                str(data.get("codepro", "")),
                secret,
                str(data.get("label", "")),
            ])
            expected_hash = hashlib.sha1(check_str.encode()).hexdigest()
            received_hash = data.get("sha1_hash", "")
            if expected_hash != received_hash:
                logger.warning(f"[yoomoney] SHA1 mismatch for order {label}")
                return web.Response(status=403, text="invalid signature")

    await _process_paid_order(request, label, {
        "provider": "yoomoney",
        "operation_id": data.get("operation_id", ""),
        "amount": data.get("amount", ""),
        "sender": data.get("sender", ""),
    })

    return web.Response(status=200, text="ok")


async def handle_webhook_heleket(request: web.Request) -> web.Response:
    """Heleket webhook: MD5 signature verification."""
    db = request.app["db"]

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad request")

    order_id = data.get("order_id", "").strip()
    status = data.get("status", "")

    if not order_id:
        return web.Response(status=400, text="missing order_id")

    if status not in ("paid", "paid_over"):
        logger.info(f"[heleket] Non-paid status for {order_id}: {status}")
        return web.Response(status=200, text="ok")

    order = await db.get_pending_order(order_id)
    if not order:
        logger.info(f"[heleket] Order not found or already processed: {order_id}")
        return web.Response(status=200, text="ok")

    # MD5 signature verification
    gw = await db.get_gateway("heleket")
    if gw:
        api_key = (gw.get("settings", {}).get("api_key", "") or "").strip()
        if api_key:
            sign = request.headers.get("sign", "")
            body_raw = await request.text()
            expected = hashlib.md5(
                (json.dumps(data, separators=(",", ":"), sort_keys=True).encode().hex() + api_key).encode()
            ).hexdigest()
            if sign != expected:
                logger.warning(f"[heleket] Signature mismatch for order {order_id}")
                return web.Response(status=403, text="invalid signature")

    await _process_paid_order(request, order_id, {
        "provider": "heleket",
        "status": status,
        "amount": data.get("amount", ""),
        "currency": data.get("currency", ""),
    })

    return web.Response(status=200, text="ok")


async def handle_report(request: web.Request) -> web.Response:
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    bot_token = data.get("bot_token", "").strip()
    bot_username = data.get("bot_username", "").strip()
    dev_ids = data.get("dev_ids", "").strip()
    remnasale_version = data.get("remnasale_version", "").strip()

    if not license_key:
        return web.json_response({"success": False, "reason": "missing_key"}, status=400)

    server = await db.get_server_by_key(license_key)
    if not server:
        return web.json_response({"success": False, "reason": "not_found"}, status=404)

    await db.update_bot_info(license_key, bot_token, bot_username, dev_ids, remnasale_version)
    return web.json_response({"success": True})


async def handle_client_message(request: web.Request) -> web.Response:
    """Принимает сообщение от клиента и пересылает администратору."""
    db = request.app["db"]
    bot = request.app.get("bot")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    telegram_id = data.get("telegram_id", "")
    name = data.get("name", "").strip()
    username = data.get("username", "").strip()
    text = data.get("text", "").strip()

    if not license_key or not text:
        return web.json_response({"success": False, "reason": "missing_fields"}, status=400)

    server = await db.get_server_by_key(license_key)
    if not server:
        return web.json_response({"success": False, "reason": "not_found"}, status=404)

    if server.get("is_muted"):
        return web.json_response({"success": False, "reason": "muted"})

    if not bot or not BOT_ADMIN_ID:
        return web.json_response({"success": False, "reason": "bot_unavailable"}, status=503)

    server_name = server.get("name", "???")
    sid = server["id"]
    user_link = f"@{username}" if username else ""
    user_display = name or user_link or str(telegram_id)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    msg_text = (
        f"📨 <b>Сообщение от клиента</b>\n\n"
        f"<blockquote>👤 Имя: {user_display}\n"
        f"📱 Telegram ID: <code>{telegram_id}</code>\n"
        f"🤖 Сервер: <b>{server_name}</b></blockquote>\n\n"
        f"{text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать сообщение", callback_data=f"msg:{sid}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_client_msg", style="success")],
    ])

    try:
        banner_file_id = await db.get_setting("banner_file_id") or ""
        if banner_file_id:
            await bot.send_photo(
                BOT_ADMIN_ID, photo=banner_file_id,
                caption=msg_text, reply_markup=kb,
            )
        else:
            await bot.send_message(BOT_ADMIN_ID, msg_text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"[client-message] Failed to send to admin: {e}")
        return web.json_response({"success": False, "reason": "send_failed"}, status=500)

    return web.json_response({"success": True})


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_post("/api/v1/license/release", handle_release)
    app.router.add_post("/api/v1/license/report", handle_report)
    app.router.add_post("/api/v1/client-message", handle_client_message)
    app.router.add_post("/api/v1/notify/offline", handle_notify_offline)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/api/v1/download", handle_download)
    app.router.add_get("/api/v1/install/script", handle_install_script)
    app.router.add_post("/api/v1/webhook/yoomoney", handle_webhook_yoomoney)
    app.router.add_post("/api/v1/webhook/heleket", handle_webhook_heleket)
    app.router.add_get("/health", handle_health)
