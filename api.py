import logging
import os
from aiohttp import web
from config import GITHUB_PAT

logger = logging.getLogger(__name__)

VERSION_FILE = os.path.join(os.path.dirname(__file__), "version")


def _read_version() -> str:
    try:
        with open(VERSION_FILE, "r") as f:
            for line in f:
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


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

    return web.json_response({"version": _read_version()})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/health", handle_health)
