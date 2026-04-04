import aiosqlite
import secrets
import os
from datetime import datetime, timedelta, timezone
from typing import Optional


PERIODS = {
    "1m": ("1 месяц", 30),
    "3m": ("3 месяца", 90),
    "6m": ("6 месяцев", 180),
    "12m": ("12 месяцев", 365),
    "unlimited": ("Бессрочно", None),
}


class LicenseDB:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    license_key TEXT UNIQUE NOT NULL,
                    server_ip TEXT DEFAULT '',
                    period TEXT NOT NULL DEFAULT '1m',
                    is_active INTEGER DEFAULT 1,
                    is_blacklisted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_check_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            # Значения по умолчанию
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('check_interval_minutes', '1')"
            )
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('offline_grace_days', '14')"
            )
            # Миграции
            cursor = await db.execute("PRAGMA table_info(servers)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "server_domain" in columns and "server_ip" not in columns:
                await db.execute("ALTER TABLE servers RENAME COLUMN server_domain TO server_ip")
            elif "server_ip" not in columns and "server_domain" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN server_ip TEXT DEFAULT ''")
            if "is_blacklisted" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN is_blacklisted INTEGER DEFAULT 0")
            await db.commit()

    async def _fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def _fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_servers(self) -> list[dict]:
        return await self._fetch_all("SELECT * FROM servers ORDER BY id")

    async def get_server(self, server_id: int) -> Optional[dict]:
        return await self._fetch_one("SELECT * FROM servers WHERE id = ?", (server_id,))

    async def get_server_by_key(self, key: str) -> Optional[dict]:
        return await self._fetch_one("SELECT * FROM servers WHERE license_key = ?", (key,))

    async def add_server(self, name: str, period: str) -> dict:
        key = secrets.token_hex(20)
        now = datetime.now(timezone.utc)

        if not name:
            servers = await self.get_all_servers()
            name = f"Сервер {len(servers) + 1}"

        _, days = PERIODS.get(period, ("", 30))
        expires = (now + timedelta(days=days)).isoformat() if days else None

        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO servers (name, license_key, period, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (name, key, period, now.isoformat(), expires),
            )
            await db.commit()
            return await self.get_server(cursor.lastrowid)

    async def toggle_server(self, server_id: int) -> Optional[dict]:
        server = await self.get_server(server_id)
        if not server:
            return None
        new_status = 0 if server["is_active"] else 1
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET is_active = ? WHERE id = ?", (new_status, server_id))
            await db.commit()
        return await self.get_server(server_id)

    async def set_server_active(self, server_id: int, is_active: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET is_active = ? WHERE id = ?", (is_active, server_id))
            await db.commit()
        return await self.get_server(server_id)

    async def blacklist_server(self, server_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET is_active = 0, is_blacklisted = 1 WHERE id = ?",
                (server_id,),
            )
            await db.commit()
        return await self.get_server(server_id)

    async def unblacklist_server(self, server_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET is_active = 1, is_blacklisted = 0 WHERE id = ?",
                (server_id,),
            )
            await db.commit()
        return await self.get_server(server_id)

    async def delete_server(self, server_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def extend_server(self, server_id: int, period: str) -> Optional[dict]:
        server = await self.get_server(server_id)
        if not server:
            return None

        _, days = PERIODS.get(period, ("", 30))

        if days is None:
            expires = None
        else:
            now = datetime.now(timezone.utc)
            if server["expires_at"]:
                current_expiry = datetime.fromisoformat(server["expires_at"])
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                base = max(current_expiry, now)
            else:
                base = now
            expires = (base + timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET expires_at = ?, period = ? WHERE id = ?",
                (expires, period, server_id),
            )
            await db.commit()
        return await self.get_server(server_id)

    async def reset_ip(self, server_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET server_ip = '' WHERE id = ?", (server_id,))
            await db.commit()
        return await self.get_server(server_id)

    async def reset_server_ip(self, server_id: int) -> Optional[dict]:
        return await self.reset_ip(server_id)

    async def reset_ip_by_key(self, key: str, server_ip: str) -> dict:
        server = await self.get_server_by_key(key)
        if not server:
            return {"success": False, "reason": "not_found"}
        if server["server_ip"] and server["server_ip"] != server_ip:
            return {"success": False, "reason": "ip_mismatch"}
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET server_ip = '' WHERE id = ?", (server["id"],))
            await db.commit()
        return {"success": True}

    async def rename_server(self, server_id: int, new_name: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET name = ? WHERE id = ?", (new_name, server_id))
            await db.commit()
        return await self.get_server(server_id)

    async def verify_license(self, key: str, server_ip: str) -> dict:
        server = await self.get_server_by_key(key)

        if not server:
            return {"valid": False, "reason": "not_found"}

        if server.get("is_blacklisted"):
            return {"valid": False, "reason": "blacklisted"}

        if not server["is_active"]:
            return {"valid": False, "reason": "suspended"}

        if server["expires_at"]:
            expires = datetime.fromisoformat(server["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                return {"valid": False, "reason": "expired"}

        if server_ip:
            if server["server_ip"] and server["server_ip"] != server_ip:
                return {"valid": False, "reason": "ip_mismatch"}
            if not server["server_ip"]:
                async with aiosqlite.connect(self.path) as db:
                    await db.execute(
                        "UPDATE servers SET server_ip = ? WHERE id = ?",
                        (server_ip, server["id"]),
                    )
                    await db.commit()

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET last_check_at = ? WHERE id = ?",
                (now, server["id"]),
            )
            await db.commit()

        offline_grace_days = await self.get_offline_grace_days()
        result = {"valid": True, "offline_grace_days": offline_grace_days}
        if server["expires_at"]:
            result["expires_at"] = server["expires_at"]
        return result

    async def check_key_valid(self, key: str) -> dict:
        server = await self.get_server_by_key(key)
        if not server:
            return {"valid": False, "reason": "not_found"}
        if not server["is_active"]:
            return {"valid": False, "reason": "suspended"}
        if server["expires_at"]:
            expires = datetime.fromisoformat(server["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                return {"valid": False, "reason": "expired"}
        return {"valid": True}

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self._fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            await db.commit()

    async def get_check_interval(self) -> int:
        val = await self.get_setting("check_interval_minutes", "1")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 1

    async def set_check_interval(self, minutes: int):
        await self.set_setting("check_interval_minutes", str(max(1, minutes)))

    async def get_offline_grace_days(self) -> int:
        val = await self.get_setting("offline_grace_days", "14")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 14

    async def set_offline_grace_days(self, days: int):
        await self.set_setting("offline_grace_days", str(max(1, days)))

    async def export_backup(self) -> dict:
        servers = await self.get_all_servers()
        interval = await self.get_check_interval()
        grace = await self.get_offline_grace_days()
        return {"servers": servers, "settings": {"check_interval_minutes": interval, "offline_grace_days": grace}}

    async def import_backup(self, data: dict):
        servers = data.get("servers", [])
        settings = data.get("settings", {})
        async with aiosqlite.connect(self.path) as db:
            for s in servers:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO servers
                    (id, name, license_key, server_ip, period, is_active, is_blacklisted, created_at, expires_at, last_check_at)
                    VALUES (:id, :name, :license_key, :server_ip, :period, :is_active, :is_blacklisted, :created_at, :expires_at, :last_check_at)
                    """,
                    {
                        "id": s.get("id"),
                        "name": s.get("name", ""),
                        "license_key": s.get("license_key", ""),
                        "server_ip": s.get("server_ip", ""),
                        "period": s.get("period", "1m"),
                        "is_active": s.get("is_active", 1),
                        "is_blacklisted": s.get("is_blacklisted", 0),
                        "created_at": s.get("created_at", ""),
                        "expires_at": s.get("expires_at"),
                        "last_check_at": s.get("last_check_at"),
                    },
                )
            for key, val in settings.items():
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, str(val)),
                )
            await db.commit()


Database = LicenseDB
