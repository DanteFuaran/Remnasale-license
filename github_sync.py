"""Background sync: pull Remnasale version + tarball from GitHub automatically."""

import asyncio
import logging
import os
import tempfile
import time

from aiohttp import ClientSession, ClientTimeout

from config import GITHUB_PAT, GITHUB_REPO, GITHUB_BRANCH, PACKAGES_DIR

logger = logging.getLogger(__name__)

_SYNC_INTERVAL = 300  # 5 minutes
_GITHUB_API = "https://api.github.com"
_GITHUB_RAW = "https://raw.githubusercontent.com"

_PRODUCT_DIR = os.path.join(PACKAGES_DIR, "remnasale")


def _parse_version(text: str) -> str:
    """Extract version string from 'version: X.Y.Z' or plain 'X.Y.Z'."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        return line.split(":", 1)[-1].strip() if ":" in line else line
    return ""


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convert '0.4.137' → (0, 4, 137) for comparison."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _read_local_version() -> str:
    """Read current local version from packages directory."""
    path = os.path.join(_PRODUCT_DIR, "version")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r") as f:
            return _parse_version(f.read())
    except Exception:
        return ""


def _write_local_version(version: str) -> None:
    os.makedirs(_PRODUCT_DIR, exist_ok=True)
    with open(os.path.join(_PRODUCT_DIR, "version"), "w") as f:
        f.write(f"version: {version}\n")


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_PAT:
        h["Authorization"] = f"token {GITHUB_PAT}"
    return h


async def _fetch_github_version(session: ClientSession) -> str | None:
    """Fetch version file content from GitHub."""
    url = f"{_GITHUB_RAW}/{GITHUB_REPO}/{GITHUB_BRANCH}/version"
    headers = {}
    if GITHUB_PAT:
        headers["Authorization"] = f"token {GITHUB_PAT}"
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return _parse_version(await resp.text())
            logger.warning(f"[github-sync] Version fetch: HTTP {resp.status}")
    except Exception as e:
        logger.warning(f"[github-sync] Version fetch error: {e}")
    return None


async def _download_tarball(session: ClientSession, version: str) -> bool:
    """Download repo tarball from GitHub and save to packages directory."""
    url = f"{_GITHUB_API}/repos/{GITHUB_REPO}/tarball/{GITHUB_BRANCH}"
    try:
        async with session.get(url, headers=_headers(), allow_redirects=True) as resp:
            if resp.status != 200:
                logger.warning(f"[github-sync] Tarball download: HTTP {resp.status}")
                return False

            os.makedirs(_PRODUCT_DIR, exist_ok=True)

            # Write to temp file first, then atomic rename
            fd, tmp_path = tempfile.mkstemp(dir=_PRODUCT_DIR, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)

                final_path = os.path.join(_PRODUCT_DIR, "remnasale.tar.gz")
                versioned_path = os.path.join(_PRODUCT_DIR, f"remnasale-{version}.tar.gz")

                os.replace(tmp_path, final_path)

                # Also save versioned copy
                try:
                    import shutil
                    shutil.copy2(final_path, versioned_path)
                except Exception:
                    pass

                return True
            except Exception:
                # Cleanup temp file on error
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    except Exception as e:
        logger.error(f"[github-sync] Tarball download error: {e}")
        return False


async def sync_once() -> bool:
    """Single sync iteration. Returns True if updated."""
    local_ver = _read_local_version()
    timeout = ClientTimeout(total=60)

    async with ClientSession(timeout=timeout) as session:
        remote_ver = await _fetch_github_version(session)
        if not remote_ver:
            return False

        if local_ver and _version_tuple(remote_ver) <= _version_tuple(local_ver):
            return False

        logger.info(f"[github-sync] New version: {local_ver or '(none)'} → {remote_ver}")

        if await _download_tarball(session, remote_ver):
            _write_local_version(remote_ver)
            logger.info(f"[github-sync] Updated to {remote_ver}")
            return True
        else:
            logger.error(f"[github-sync] Failed to download tarball for {remote_ver}")
            return False


async def github_sync_loop():
    """Background loop: check GitHub for new Remnasale version every 5 minutes."""
    await asyncio.sleep(10)  # Let server start up first
    logger.info("[github-sync] Started (interval=%ds)", _SYNC_INTERVAL)

    while True:
        try:
            updated = await sync_once()
            if updated:
                logger.info("[github-sync] Sync complete — new version available")
        except Exception as e:
            logger.error(f"[github-sync] Unexpected error: {e}")

        await asyncio.sleep(_SYNC_INTERVAL)
