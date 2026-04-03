import logging
import os
import io
import tarfile
from aiohttp import web
import aiohttp
from config import GITHUB_PAT, GITHUB_REPO, SETUP_DIR

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

    # Всегда возвращаем check_interval
    check_interval = await db.get_check_interval()
    result["check_interval"] = check_interval

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

    script_path = os.path.join(SETUP_DIR, "remnasale-install.sh")
    if os.path.isfile(script_path):
        with open(script_path, "r") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/plain")

    # Fallback to GitHub
    if not GITHUB_PAT or not GITHUB_REPO:
        return web.Response(status=503, text="Install script not found")

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


async def handle_bootstrap(request: web.Request) -> web.Response:
    """Serve the bootstrap install-license.sh script (no auth required)."""
    script_path = os.path.join(SETUP_DIR, "install-license.sh")
    if not os.path.isfile(script_path):
        return web.Response(status=503, text="Bootstrap script not found")
    with open(script_path, "r") as f:
        content = f.read()
    return web.Response(text=content, content_type="text/plain")


async def handle_archive(request: web.Request) -> web.Response:
    """Serve a tarball of the setup directory for installation/updates."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.Response(status=403, text=result.get("reason", "invalid"))

    if not os.path.isdir(SETUP_DIR):
        return web.Response(status=503, text="Setup directory not found")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for entry in os.listdir(SETUP_DIR):
            if entry == ".git":
                continue
            full_path = os.path.join(SETUP_DIR, entry)
            tar.add(full_path, arcname=f"remnasale/{entry}")
    buf.seek(0)
    return web.Response(
        body=buf.read(),
        content_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=remnasale.tar.gz"},
    )


async def handle_version(request: web.Request) -> web.Response:
    """Return the current version from the setup directory."""
    db = request.app["db"]
    key = request.query.get("key", "").strip()

    if not key:
        return web.Response(status=401, text="Missing license key")

    result = await db.check_key_valid(key)
    if not result["valid"]:
        return web.json_response({"error": result.get("reason", "invalid")}, status=403)

    version_file = os.path.join(SETUP_DIR, "version")
    version = "unknown"
    if os.path.isfile(version_file):
        with open(version_file, "r") as f:
            for line in f:
                if line.startswith("version:"):
                    version = line.split(":", 1)[1].strip()
                    break

    return web.json_response({"version": version})


def setup_routes(app: web.Application):
    app.router.add_post("/api/v1/license/verify", handle_verify)
    app.router.add_get("/api/v1/install/script", handle_install_script)
    app.router.add_get("/api/v1/install/archive", handle_archive)
    app.router.add_get("/api/v1/install/bootstrap", handle_bootstrap)
    app.router.add_get("/api/v1/version", handle_version)
    app.router.add_get("/health", handle_health)
