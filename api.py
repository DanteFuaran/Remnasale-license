import logging
from aiohttp import web
import aiohttp
from config import GITHUB_PAT, GITHUB_REPO

logger = logging.getLogger(__name__)


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

    if result.get("valid") and GITHUB_PAT:
        result["token"] = GITHUB_PAT

    status = 200 if result["valid"] else 403
    return web.json_response(result, status=status)


async def handle_install_script(request: web.Request) -> web.Response:
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.Response(status=403, text=result.get("reason", "invalid"))

    if not GITHUB_PAT or not GITHUB_REPO:
        return web.Response(status=503, text="GitHub not configured")

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"token {GITHUB_PAT}",
                "Accept": "application/vnd.github.v3.raw",
            }
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/remnasale-install.sh"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    return web.Response(text=content, content_type="text/plain")
                return web.Response(status=502, text="Failed to fetch from GitHub")
    except Exception as e:
        logger.error(f"Error fetching install script: {e}")
        return web.Response(status=500, text="Internal error")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_get("/api/v1/install/script", handle_install_script)
    app.router.add_get("/health", handle_health)
