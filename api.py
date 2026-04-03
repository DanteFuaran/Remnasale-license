import logging
import os
import time
from aiohttp import web, ClientSession, ClientTimeout
from config import GITHUB_PAT, GITHUB_REPO

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


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_post("/api/v1/license/release", handle_release)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/api/v1/download", handle_download)
    app.router.add_get("/health", handle_health)
