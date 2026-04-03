# 🔑 Remnasale License

Лицензионный сервер для управления доступом к [Remnasale](https://github.com/DanteFuaran/Remnasale).

Telegram-бот + REST API для выдачи, продления и отзыва лицензий. Каждый клиент получает уникальный ключ, привязанный к IP его сервера. Проверка происходит раз в 3 дня — при невалидной лицензии бот останавливается.

---

## 🚀 Установка

```bash
git clone https://github.com/DanteFuaran/Remnasale-license.git /opt/remnasale-license
cd /opt/remnasale-license
cp .env.example .env
# Заполнить .env (см. ниже)
docker compose up -d
```

---

## ⚙️ Конфигурация `.env`

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота (получить у [@BotFather](https://t.me/BotFather)) |
| `BOT_ADMIN_ID` | Telegram ID администратора |
| `API_HOST` | Адрес для API (по умолчанию `0.0.0.0`) |
| `API_PORT` | Порт API (по умолчанию `8080`) |
| `DATABASE_PATH` | Путь к SQLite базе (по умолчанию `/data/license.db`) |
| `GITHUB_PAT` | GitHub PAT с доступом к репозиторию Remnasale (scope: `repo`) |
| `GITHUB_REPO` | Репозиторий (по умолчанию `DanteFuaran/Remnasale`) |

---

## 📡 API

### `POST /api/v1/license/verify`

Проверка лицензии (вызывается Remnasale каждые 3 дня).

```json
// Запрос
{ "license_key": "abc123", "server_ip": "1.2.3.4" }

// Ответ 200 (валидна)
{ "valid": true, "token": "<github_pat>", "expires_at": "2026-07-01T00:00:00+00:00" }

// Ответ 403 (невалидна)
{ "valid": false, "reason": "suspended" }
```

Возможные причины отказа: `not_found`, `suspended`, `expired`, `ip_mismatch`.

### `GET /api/v1/install/script?key=<license_key>`

Скачивает установочный скрипт Remnasale (если ключ валиден).

### `GET /health`

```json
{ "status": "ok" }
```

---

## 🤖 Управление через бота

После запуска напишите боту `/start`. Доступны команды:

- **Добавить сервер** — выбрать период (1/3/6/12 мес или бессрочно), получить ключ
- **Просмотр сервера** — ключ, IP, статус, срок действия, последняя проверка
- **Продлить** — добавить период к текущему сроку
- **Приостановить / Возобновить** — немедленно блокирует/разблокирует лицензию
- **Сбросить IP** — позволяет переустановить бот на другой сервер
- **Переименовать** — задать удобное имя серверу
- **Удалить** — безвозвратно удалить лицензию

---

## 🔄 Обновление

```bash
cd /opt/remnasale-license
git pull origin main
docker compose up -d --build
```

---

## 🗂️ Структура проекта

```
.
├── main.py           # Точка входа (бот + API)
├── config.py         # Конфигурация из .env
├── database.py       # SQLite, вся логика лицензий
├── api.py            # HTTP API (aiohttp)
├── bot/
│   ├── handlers.py   # Telegram-хендлеры
│   └── keyboards.py  # Клавиатуры
├── Dockerfile
├── docker-compose.yml
└── .env.example
```
