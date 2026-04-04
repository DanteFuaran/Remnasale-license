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


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_post("/api/v1/license/release", handle_release)
    app.router.add_post("/api/v1/license/report", handle_report)
    app.router.add_post("/api/v1/notify/offline", handle_notify_offline)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/api/v1/download", handle_download)
    app.router.add_get("/api/v1/install/script", handle_install_script)
    app.router.add_get("/health", handle_health)
