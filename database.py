import aiosqlite
import json
import secrets
import uuid
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

GATEWAY_TYPES = {
    "yoomoney": {
        "label": "💳 ЮМани",
        "fields": {"wallet_id": "Кошелек", "secret_key": "Секретный ключ"},
        "copyable": {"wallet_id"},
    },
    "heleket": {
        "label": "🌐 Heleket",
        "fields": {"merchant_id": "Мерчант", "api_key": "API Ключ"},
        "copyable": set(),
    },
    "stars": {"label": "⭐ Telegram Stars", "fields": {}},
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
            if "bot_token" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN bot_token TEXT DEFAULT ''")
            if "bot_username" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN bot_username TEXT DEFAULT ''")
            if "dev_telegram_ids" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN dev_telegram_ids TEXT DEFAULT ''")
            if "remnasale_version" not in columns:
                await db.execute("ALTER TABLE servers ADD COLUMN remnasale_version TEXT DEFAULT ''")

            # Платёжные шлюзы
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payment_gateways (
                    type TEXT PRIMARY KEY,
                    is_active INTEGER DEFAULT 0,
                    settings TEXT DEFAULT '{}'
                )
            """)
            for gtype in GATEWAY_TYPES:
                await db.execute(
                    "INSERT OR IGNORE INTO payment_gateways (type, is_active, settings) VALUES (?, 0, '{}')",
                    (gtype,),
                )
            # Migrate: add order_index column if missing
            cursor2 = await db.execute("PRAGMA table_info(payment_gateways)")
            gw_columns = [row[1] for row in await cursor2.fetchall()]
            if "order_index" not in gw_columns:
                await db.execute("ALTER TABLE payment_gateways ADD COLUMN order_index INTEGER DEFAULT NULL")
            # Default currency setting
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_currency', 'RUB')"
            )

            # Заказы (покупки лицензий)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    products TEXT NOT NULL DEFAULT '[]',
                    duration TEXT NOT NULL DEFAULT '1m',
                    amount INTEGER NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'RUB',
                    gateway TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    paid_at TEXT,
                    payment_url TEXT DEFAULT '',
                    payment_data TEXT DEFAULT '{}'
                )
            """)

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

    async def update_bot_info(self, license_key: str, bot_token: str, bot_username: str, dev_ids: str, remnasale_version: str = ""):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE servers SET bot_token = ?, bot_username = ?, dev_telegram_ids = ?, remnasale_version = ? WHERE license_key = ?",
                (bot_token, bot_username, dev_ids, remnasale_version, license_key),
            )
            await db.commit()

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

    async def find_servers_by_dev_id(self, telegram_id: int) -> list[dict]:
        servers = await self.get_all_servers()
        tid_str = str(telegram_id)
        result = []
        for s in servers:
            dev_ids = (s.get("dev_telegram_ids", "") or "").split(",")
            if tid_str in [t.strip() for t in dev_ids if t.strip()]:
                result.append(s)
        return result

    # ── Платёжные шлюзы ────────────────────────────────────────────

    async def get_all_gateways(self) -> list[dict]:
        rows = await self._fetch_all("SELECT * FROM payment_gateways ORDER BY CASE WHEN order_index IS NULL THEN 999 ELSE order_index END, type")
        for r in rows:
            r["settings"] = json.loads(r.get("settings") or "{}")
        return rows

    async def get_gateway(self, gtype: str) -> Optional[dict]:
        row = await self._fetch_one("SELECT * FROM payment_gateways WHERE type = ?", (gtype,))
        if row:
            row["settings"] = json.loads(row.get("settings") or "{}")
        return row

    async def toggle_gateway(self, gtype: str) -> Optional[dict]:
        gw = await self.get_gateway(gtype)
        if not gw:
            return None
        new_val = 0 if gw["is_active"] else 1
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE payment_gateways SET is_active = ? WHERE type = ?", (new_val, gtype))
            await db.commit()
        return await self.get_gateway(gtype)

    async def update_gateway_field(self, gtype: str, field: str, value: str) -> Optional[dict]:
        gw = await self.get_gateway(gtype)
        if not gw:
            return None
        settings = gw["settings"]
        settings[field] = value
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE payment_gateways SET settings = ? WHERE type = ?",
                (json.dumps(settings, ensure_ascii=False), gtype),
            )
            await db.commit()
        return await self.get_gateway(gtype)

    async def clear_gateway_field(self, gtype: str, field: str) -> Optional[dict]:
        gw = await self.get_gateway(gtype)
        if not gw:
            return None
        settings = gw["settings"]
        settings.pop(field, None)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE payment_gateways SET settings = ? WHERE type = ?",
                (json.dumps(settings, ensure_ascii=False), gtype),
            )
            await db.commit()
        return await self.get_gateway(gtype)

    async def set_gateway_order(self, ordered_types: list[str]):
        """Set order_index for each gateway type based on provided list order."""
        async with aiosqlite.connect(self.path) as db:
            for idx, gtype in enumerate(ordered_types):
                await db.execute(
                    "UPDATE payment_gateways SET order_index = ? WHERE type = ?",
                    (idx, gtype),
                )
            await db.commit()

    async def export_backup(self) -> dict:
        servers = await self.get_all_servers()
        interval = await self.get_check_interval()
        grace = await self.get_offline_grace_days()
        support = await self.get_setting("support_url")
        community = await self.get_setting("community_url")
        gateways = await self.get_all_gateways()
        return {
            "servers": servers,
            "settings": {
                "check_interval_minutes": interval,
                "offline_grace_days": grace,
                "support_url": support,
                "community_url": community,
            },
            "payment_gateways": gateways,
        }

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
            for gw in data.get("payment_gateways", []):
                s = gw.get("settings", {})
                await db.execute(
                    "INSERT OR REPLACE INTO payment_gateways (type, is_active, settings) VALUES (?, ?, ?)",
                    (gw["type"], gw.get("is_active", 0), json.dumps(s, ensure_ascii=False)),
                )
            await db.commit()

    # ── Заказы ─────────────────────────────────────────────────────────

    async def create_order(
        self,
        user_id: int,
        products: list[str],
        duration: str,
        amount: int,
        currency: str,
        gateway: str,
    ) -> dict:
        order_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO orders (id, user_id, products, duration, amount, currency, gateway, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (order_id, user_id, json.dumps(products), duration, amount, currency, gateway, now),
            )
            await db.commit()
        return await self.get_order(order_id)

    async def get_order(self, order_id: str) -> Optional[dict]:
        row = await self._fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        if row:
            row["products"] = json.loads(row.get("products") or "[]")
            row["payment_data"] = json.loads(row.get("payment_data") or "{}")
        return row

    async def update_order_payment_url(self, order_id: str, url: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET payment_url = ? WHERE id = ?", (url, order_id)
            )
            await db.commit()

    async def complete_order(self, order_id: str, payment_data: dict | None = None) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        pd = json.dumps(payment_data or {}, ensure_ascii=False)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET status = 'paid', paid_at = ?, payment_data = ? WHERE id = ? AND status = 'pending'",
                (now, pd, order_id),
            )
            await db.commit()
        return await self.get_order(order_id)

    async def fail_order(self, order_id: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE orders SET status = 'failed' WHERE id = ? AND status = 'pending'",
                (order_id,),
            )
            await db.commit()

    async def get_pending_order(self, order_id: str) -> Optional[dict]:
        row = await self._fetch_one(
            "SELECT * FROM orders WHERE id = ? AND status = 'pending'", (order_id,)
        )
        if row:
            row["products"] = json.loads(row.get("products") or "[]")
            row["payment_data"] = json.loads(row.get("payment_data") or "{}")
        return row

    async def add_server_for_user(self, user_id: int, products: list[str], duration: str) -> dict:
        """Создаёт сервер и привязывает к telegram_id пользователя."""
        key = secrets.token_hex(20)
        now = datetime.now(timezone.utc)
        product_names = ", ".join(products)
        name = f"Сервер ({product_names})"

        duration_days = {"1m": 30, "3m": 90, "6m": 180, "12m": 365}
        days = duration_days.get(duration, 30)
        expires = (now + timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """INSERT INTO servers (name, license_key, period, created_at, expires_at, dev_telegram_ids)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, key, duration, now.isoformat(), expires, str(user_id)),
            )
            await db.commit()
            return await self.get_server(cursor.lastrowid)


Database = LicenseDB
