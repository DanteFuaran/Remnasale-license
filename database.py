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
                    server_domain TEXT DEFAULT '',
                    period TEXT NOT NULL DEFAULT '1m',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_check_at TEXT
                )
            """)
            # Миграция: переименование server_ip -> server_domain
            cursor = await db.execute("PRAGMA table_info(servers)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "server_ip" in columns and "server_domain" not in columns:
                await db.execute("ALTER TABLE servers RENAME COLUMN server_ip TO server_domain")
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

    async def add_server(self, period: str) -> dict:
        key = secrets.token_hex(20)
        now = datetime.now(timezone.utc)

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

    async def reset_domain(self, server_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET server_domain = '' WHERE id = ?", (server_id,))
            await db.commit()
        return await self.get_server(server_id)

    async def rename_server(self, server_id: int, new_name: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE servers SET name = ? WHERE id = ?", (new_name, server_id))
            await db.commit()
        return await self.get_server(server_id)

    async def verify_license(self, key: str, server_domain: str) -> dict:
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

        if server_domain:
            if server["server_domain"] and server["server_domain"] != server_domain:
                return {"valid": False, "reason": "domain_mismatch"}
            if not server["server_domain"]:
                async with aiosqlite.connect(self.path) as db:
                    await db.execute(
                        "UPDATE servers SET server_domain = ? WHERE id = ?",
                        (server_domain, server["id"]),
                    )
                    await db.commit()

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET last_check_at = ? WHERE id = ?",
                (now, server["id"]),
            )
            await db.commit()

        result = {"valid": True}
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
