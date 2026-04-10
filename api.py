import hashlib
import json
import logging
import os
import time
from aiohttp import web, ClientSession, ClientTimeout
from config import BOT_ADMIN_ID, PACKAGES_DIR, LICENSE_SERVER_URL, GITHUB_PAT, GITHUB_REPO, GITHUB_BRANCH

logger = logging.getLogger(__name__)

# ── Cached Remnasale version ──────────────────────────────────────────
_CACHE_TTL = 300  # 5 minutes
_cached_version: str | None = None
_cached_at: float = 0.0

# ── Product version cache ─────────────────────────────────────────────
_product_version_cache: dict[str, tuple[str, float]] = {}


def _fetch_remnasale_version() -> str:
    """Read Remnasale version from packages directory."""
    global _cached_version, _cached_at

    now = time.monotonic()
    if _cached_version and (now - _cached_at) < _CACHE_TTL:
        return _cached_version

    version_file = os.path.join(PACKAGES_DIR, "remnasale", "version")
    if not os.path.exists(version_file):
        return _cached_version or "unknown"

    try:
        with open(version_file, "r") as f:
            for line in f:
                if line.strip():
                    # plain version or "version: X.Y.Z"
                    v = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                    _cached_version = v
                    _cached_at = now
                    return v
    except Exception as e:
        logger.warning(f"[version] Failed to read remnasale version: {e}")

    return _cached_version or "unknown"


async def handle_verify(request: web.Request) -> web.Response:
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"valid": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    server_ip = data.get("server_ip", "").strip()
    install_mode = bool(data.get("install", False))

    if not license_key:
        return web.json_response({"valid": False, "reason": "missing_key"}, status=400)

    result = await db.verify_license(license_key, server_ip, install_mode=install_mode)

    check_interval = await db.get_check_interval()
    result["check_interval"] = check_interval

    if "offline_grace_days" not in result:
        offline_grace_days = await db.get_offline_grace_days()
        result["offline_grace_days"] = offline_grace_days

    license_host = await db.get_setting("license_host")
    if license_host:
        result["license_host"] = license_host

    support_url = await db.get_setting("support_url")
    if support_url:
        result["support_url"] = support_url

    # Настройки донатов
    donate_enabled = (await db.get_setting("donate_enabled")) == "1"
    donate_muted = result.get("donate_muted", False)
    result["donate"] = {"enabled": donate_enabled and not donate_muted}
    if donate_enabled:
        result["donate"]["message"] = await db.get_setting("donate_message")
        buttons = []
        for i in range(1, 4):
            if (await db.get_setting(f"donate_btn{i}_enabled")) == "1":
                label = await db.get_setting(f"donate_btn{i}_label")
                url = await db.get_setting(f"donate_btn{i}_url")
                if label and url:
                    buttons.append({"label": label, "url": url})
        result["donate"]["buttons"] = buttons

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

    version = _fetch_remnasale_version()
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
    """Serve Remnasale tarball from packages directory (legacy endpoint)."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    tarball = os.path.join(PACKAGES_DIR, "remnasale", "remnasale.tar.gz")
    if not os.path.exists(tarball):
        return web.json_response({"error": "package_not_found"}, status=404)

    return web.FileResponse(
        tarball,
        headers={
            "Content-Type": "application/gzip",
            "Content-Disposition": "attachment; filename=remnasale.tar.gz",
        },
    )


# ── Cached install script from GitHub ─────────────────────────────────
_install_script_cache: str | None = None
_install_script_cached_at: float = 0.0
_INSTALL_SCRIPT_TTL = 300  # 5 minutes


async def _fetch_install_script_from_github() -> str | None:
    """Download remnasale-install.sh from private GitHub repo."""
    global _install_script_cache, _install_script_cached_at

    now = time.monotonic()
    if _install_script_cache and (now - _install_script_cached_at) < _INSTALL_SCRIPT_TTL:
        return _install_script_cache

    if not GITHUB_PAT or not GITHUB_REPO:
        return None

    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/remnasale-install.sh"
    headers = {"Authorization": f"token {GITHUB_PAT}"}
    try:
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    _install_script_cache = await resp.text()
                    _install_script_cached_at = now
                    return _install_script_cache
                else:
                    logger.warning(f"[install-script] GitHub returned {resp.status}")
    except Exception as e:
        logger.warning(f"[install-script] GitHub fetch error: {e}")
    return _install_script_cache  # return stale cache if available


async def handle_install_script(request: web.Request) -> web.Response:
    """Serve the Remnasale install script from packages directory or GitHub."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    # 1. Try local file
    script_path = os.path.join(PACKAGES_DIR, "remnasale", "install.sh")
    if os.path.exists(script_path):
        try:
            with open(script_path, "r") as f:
                script = f.read()
            return web.Response(
                text=script,
                content_type="text/plain",
                headers={"Cache-Control": "no-cache"},
            )
        except Exception as e:
            logger.error(f"[install-script] Error reading local file: {e}")

    # 2. Fallback: download from GitHub
    script = await _fetch_install_script_from_github()
    if script:
        return web.Response(
            text=script,
            content_type="text/plain",
            headers={"Cache-Control": "no-cache"},
        )

    return web.Response(status=404, text="Install script not available")


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
    server_id = server["id"] if server else None

    # Синхронизируем monitor_silent_ids в БД
    if server_id is not None:
        import json as _json
        _raw = await db.get_setting("monitor_silent_ids", "")
        try:
            _silent = set(int(x) for x in _json.loads(_raw)) if _raw else set()
        except Exception:
            _silent = set()
        changed = False
        if event == "offline" and server_id not in _silent:
            _silent.add(server_id)
            changed = True
        elif event in ("online", "installed") and server_id in _silent:
            _silent.discard(server_id)
            changed = True
        elif event == "uninstalled" and server_id in _silent:
            _silent.discard(server_id)
            changed = True
        if changed:
            await db.set_setting("monitor_silent_ids", _json.dumps(list(_silent)))

    if bot and BOT_ADMIN_ID:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        if event == "installed":
            # Формируем детали: имя бота, telegram_id владельца
            bot_username = (server.get("bot_username", "") if server else "") or ""
            owner_id = (server.get("owner_telegram_id", "") if server else "") or ""
            dev_ids_raw = (server.get("dev_telegram_ids", "") if server else "") or ""
            display_tg_id = owner_id or (dev_ids_raw.split(",")[0].strip() if dev_ids_raw else "")

            # Получаем имя и username владельца
            owner_name = "—"
            owner_username = None
            if owner_id:
                try:
                    user = await db.get_user(int(owner_id))
                    if user:
                        owner_name = user.get("full_name") or user.get("username") or f"ID {owner_id}"
                        owner_username = user.get("username")
                except Exception:
                    pass
            # Формируем строку имени с ссылкой
            if owner_name != "—" and owner_username:
                owner_line = f"{owner_name} (https://t.me/{owner_username})"
            else:
                owner_line = owner_name

            text = (
                f"🟢 <b>Успешное подключение!</b>\n\n"
                f"Сервер: <code>{server_name}</code>\n"
                f"Имя:  {owner_line}\n"
                f"Телеграм ID: <code>{display_tg_id or '—'}</code>\n"
                f"IP: <code>{server_ip or '—'}</code>\n"
                f"Бот: {('@' + bot_username) if bot_username else '—'}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_notify_offline")],
            ])
        elif event == "uninstalled":
            text = (
                f"🗑 <b>Remnasale удалён!</b>\n\n"
                f"Сервер: <b>{server_name}</b>\n"
                f"IP: <code>{server_ip or '—'}</code>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_notify_offline")],
            ])
        elif event == "online":
            text = (
                f"\U0001f7e2 <b>Связь восстановлена!</b>\n\n"
                f"Сервер: <b>{server_name}</b>\n"
                f"IP: <code>{server_ip}</code>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Закрыть", callback_data="dismiss_notify_offline")],
            ])
        else:
            text = (
                f"\U0001f534 <b>Связь потеряна!</b>\n\n"
                f"Сервер: <b>{server_name}</b>\n"
                f"IP: <code>{server_ip}</code>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Закрыть", callback_data="dismiss_notify_offline")],
            ])
        try:
            await bot.send_message(BOT_ADMIN_ID, text, reply_markup=kb)
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
    owner_telegram_id = data.get("owner_telegram_id", "").strip()

    if not license_key:
        return web.json_response({"success": False, "reason": "missing_key"}, status=400)

    server = await db.get_server_by_key(license_key)
    if not server:
        return web.json_response({"success": False, "reason": "not_found"}, status=404)

    await db.update_bot_info(license_key, bot_token, bot_username, dev_ids, remnasale_version, owner_telegram_id)
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
        [InlineKeyboardButton(text="✉️ Ответить", callback_data=f"qreply:{sid}")],
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


async def handle_banner(request: web.Request) -> web.Response:
    """Serve the license server banner image."""
    banner_path = os.path.join(os.path.dirname(__file__), "default_banner.jpg")
    if not os.path.exists(banner_path):
        return web.Response(status=404, text="Banner not found")
    return web.FileResponse(banner_path)


# ── Product-based endpoints (for DFC Manager) ─────────────────────────

def _read_product_version(product: str) -> str:
    """Read version from product's version file in packages directory."""
    now = time.monotonic()
    cached = _product_version_cache.get(product)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    version_file = os.path.join(PACKAGES_DIR, product, "version")
    if not os.path.exists(version_file):
        return "unknown"

    try:
        with open(version_file, "r") as f:
            for line in f:
                if line.startswith("version:"):
                    ver = line.split(":", 1)[1].strip()
                    _product_version_cache[product] = (ver, now)
                    return ver
    except Exception as e:
        logger.warning(f"[product-version] Failed to read {product} version: {e}")

    return "unknown"


async def handle_product_verify(request: web.Request) -> web.Response:
    """Verify license key for a specific product and bind to IP."""
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"valid": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    product = data.get("product", "").strip()
    server_ip = data.get("server_ip", "").strip()

    if not license_key or not product:
        return web.json_response({"valid": False, "reason": "missing_fields"}, status=400)

    result = await db.verify_product(license_key, product, server_ip)
    status = 200 if result.get("valid") else 403
    return web.json_response(result, status=status)


async def handle_product_download(request: web.Request) -> web.Response:
    """Download a product tarball (requires valid license key)."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()
    product = request.query.get("product", "").strip()

    if not key or not product:
        return web.Response(status=400, text="Missing key or product")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    # Check product is included in key
    server = await db.get_server_by_key(key)
    if server:
        products = json.loads(server.get("products") or '["remnasale"]')
        if product not in products:
            return web.json_response({"error": "product_not_included"}, status=403)

    tarball = os.path.join(PACKAGES_DIR, product, f"{product}.tar.gz")
    if not os.path.exists(tarball):
        return web.json_response({"error": "package_not_found"}, status=404)

    return web.FileResponse(
        tarball,
        headers={
            "Content-Type": "application/gzip",
            "Content-Disposition": f"attachment; filename={product}.tar.gz",
        },
    )


async def handle_product_version(request: web.Request) -> web.Response:
    """Get the latest version of a product."""
    product = request.query.get("product", "").strip()
    if not product:
        return web.Response(status=400, text="Missing product")

    version = _read_product_version(product)
    return web.json_response({"product": product, "version": version})


async def handle_manager_install(request: web.Request) -> web.Response:
    """Serve the DFC Manager install script (public, no auth required)."""
    script_path = os.path.join(PACKAGES_DIR, "dfc-manager", "install.sh")
    if not os.path.exists(script_path):
        return web.Response(status=404, text="Install script not found")

    try:
        with open(script_path, "r") as f:
            script = f.read()
        return web.Response(
            text=script,
            content_type="text/plain",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception as e:
        logger.error(f"[manager-install] Error: {e}")
        return web.Response(status=500, text="Failed to serve install script")


async def handle_manager_download(request: web.Request) -> web.Response:
    """Serve the DFC Manager tarball (public, no auth required)."""
    tarball = os.path.join(PACKAGES_DIR, "dfc-manager", "dfc-manager.tar.gz")
    if not os.path.exists(tarball):
        return web.json_response({"error": "package_not_found"}, status=404)

    return web.FileResponse(
        tarball,
        headers={
            "Content-Type": "application/gzip",
            "Content-Disposition": "attachment; filename=dfc-manager.tar.gz",
        },
    )


async def handle_manager_version(request: web.Request) -> web.Response:
    """Get the latest DFC Manager version (public)."""
    version = _read_product_version("dfc-manager")
    return web.json_response({"version": version})


async def handle_product_release_ip(request: web.Request) -> web.Response:
    """Release IP binding for a specific product."""
    db = request.app["db"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "reason": "invalid_body"}, status=400)

    license_key = data.get("license_key", "").strip()
    product = data.get("product", "").strip()

    if not license_key or not product:
        return web.json_response({"success": False, "reason": "missing_fields"}, status=400)

    server = await db.get_server_by_key(license_key)
    if not server:
        return web.json_response({"success": False, "reason": "not_found"}, status=404)

    result = await db.reset_product_ip(server["id"], product)
    if result:
        return web.json_response({"success": True})
    return web.json_response({"success": False, "reason": "unknown_product"}, status=400)


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_post("/api/v1/license/release", handle_release)
    app.router.add_get("/api/v1/license/banner", handle_banner)
    app.router.add_post("/api/v1/license/report", handle_report)
    app.router.add_post("/api/v1/client-message", handle_client_message)
    app.router.add_post("/api/v1/notify/offline", handle_notify_offline)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/api/v1/download", handle_download)
    app.router.add_get("/api/v1/install/script", handle_install_script)
    app.router.add_post("/api/v1/webhook/yoomoney", handle_webhook_yoomoney)
    app.router.add_post("/api/v1/webhook/heleket", handle_webhook_heleket)
    # Product-based endpoints (DFC Manager ecosystem)
    app.router.add_post("/api/v1/product/verify", handle_product_verify)
    app.router.add_get("/api/v1/product/download", handle_product_download)
    app.router.add_get("/api/v1/product/version", handle_product_version)
    app.router.add_post("/api/v1/product/release", handle_product_release_ip)
    # DFC Manager distribution (public, no auth)
    app.router.add_get("/api/v1/manager/install", handle_manager_install)
    app.router.add_get("/api/v1/manager/download", handle_manager_download)
    app.router.add_get("/api/v1/manager/version", handle_manager_version)
    app.router.add_get("/health", handle_health)
