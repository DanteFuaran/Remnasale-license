from datetime import datetime, timezone, timedelta
from bot.keyboards.common import server_status, PERIOD_LABELS

MSK_OFFSET = timedelta(hours=3)


def format_user_server(server: dict) -> str:
    emoji, status_text = server_status(server)

    name = server.get("name", "") or "Отсутствует"

    owner_id = (server.get("owner_telegram_id", "") or "").strip()
    if not owner_id:
        dev_ids_raw = server.get("dev_telegram_ids", "") or ""
        owner_id = dev_ids_raw.split(",")[0].strip() if dev_ids_raw else ""
    tg_id_display = f"<code>{owner_id}</code>" if owner_id else "Отсутствует"

    bot_username = server.get("bot_username", "") or ""
    bot_link = f"@{bot_username}" if bot_username else "Отсутствует"

    sip = server.get("server_ip") or ""
    ip_display = f"<code>{sip}</code>" if sip else "Отсутствует"

    remnasale_ver = server.get("remnasale_version", "") or ""
    ver_suffix = f" {remnasale_ver}" if remnasale_ver else ""

    created = "—"
    try:
        dt = datetime.fromisoformat(server["created_at"])
        created = dt.strftime("%d.%m.%Y")
    except Exception:
        pass

    if not server.get("expires_at"):
        expires = "♾️"
    else:
        try:
            dt = datetime.fromisoformat(server["expires_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_msk = dt + MSK_OFFSET
            expires = dt_msk.strftime("%d.%m.%Y %H:%M") + " (МСК)"
        except Exception:
            expires = "—"

    period_code = server.get("period") or "—"
    period_label = PERIOD_LABELS.get(period_code, period_code)
    if period_code == "unlimited":
        period_label = "♾️"

    key = server.get("license_key", "—")

    return (
        f"👤 <b>Профиль</b>\n"
        f"<blockquote>👤 Имя: {name}\n"
        f"📱 Телеграм ID: {tg_id_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Remnasale{ver_suffix}</b>\n"
        f"<blockquote>{emoji} Статус: {status_text}\n"
        f"🤖 Телеграм бот: {bot_link}\n"
        f"🌐 IP: {ip_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Support</b>\n"
        f"<blockquote>⭕ Статус: Не куплено\n"
        f"🤖 Телеграм бот: Отсутствует\n"
        f"🌐 IP: Отсутствует</blockquote>\n"
        f"\n"
        f"🔑 <b>Активация</b>\n"
        f"<blockquote>📅 Добавлен: {created}\n"
        f"⏳ Истекает: {expires}\n"
        f"🗓 Длительность: {period_label}</blockquote>"
    )


def _pluralize_servers(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return f"{n} серверов"
    r = n % 10
    if r == 1:
        return f"{n} сервер"
    elif 2 <= r <= 4:
        return f"{n} сервера"
    return f"{n} серверов"


def format_server(server: dict) -> str:
    emoji, status_text = server_status(server)

    name = server.get("name", "") or "Отсутствует"

    sip = server.get("server_ip") or ""
    ip_display = f"<code>{sip}</code>" if sip else "Отсутствует"

    owner_id = (server.get("owner_telegram_id", "") or "").strip()
    if not owner_id:
        dev_ids_raw = server.get("dev_telegram_ids", "") or ""
        owner_id = dev_ids_raw.split(",")[0].strip() if dev_ids_raw else ""
    tg_id_display = f"<code>{owner_id}</code>" if owner_id else "Отсутствует"

    bot_username = server.get("bot_username", "") or ""
    bot_link = f"@{bot_username}" if bot_username else "Отсутствует"

    remnasale_ver = server.get("remnasale_version", "") or ""
    ver_suffix = f" {remnasale_ver}" if remnasale_ver else ""

    created = "—"
    try:
        dt = datetime.fromisoformat(server["created_at"])
        created = dt.strftime("%d.%m.%Y")
    except Exception:
        pass

    if not server.get("expires_at"):
        expires = "♾️"
    else:
        try:
            dt = datetime.fromisoformat(server["expires_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_msk = dt + MSK_OFFSET
            expires = dt_msk.strftime("%d.%m.%Y %H:%M") + " (МСК)"
        except Exception:
            expires = "—"

    period_code = server.get("period") or "—"
    period_label = PERIOD_LABELS.get(period_code, period_code)
    if period_code == "unlimited":
        period_label = "♾️"

    key = server.get("license_key", "—")

    muted_line = "🔇 Уведомления: Заглушён\n" if server.get("is_muted") else ""

    return (
        f"👤 <b>Профиль</b>\n"
        f"<blockquote>👤 Имя: {name}\n"
        f"📱 Телеграм ID: {tg_id_display}</blockquote>\n"
        f"\n"
        f"📦 <b>Remnasale{ver_suffix}</b>\n"
        f"<blockquote>{emoji} Статус: {status_text}\n"
        f"🤖 Телеграм бот: {bot_link}\n"
        f"🌐 IP: {ip_display}\n"
        f"{muted_line}</blockquote>\n"
        f"\n"
        f"📦 <b>Support</b>\n"
        f"<blockquote>⭕ Статус: Не куплено\n"
        f"🤖 Телеграм бот: Отсутствует\n"
        f"🌐 IP: Отсутствует</blockquote>\n"
        f"\n"
        f"🔑 <b>Активация</b>\n"
        f"<blockquote>📅 Добавлен: {created}\n"
        f"⏳ Истекает: {expires}\n"
        f"🗓 Длительность: {period_label}</blockquote>"
    )


def clients_header(count: int) -> str:
    return f"📋 <b>Список серверов:</b> {_pluralize_servers(count)}"
