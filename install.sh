#!/bin/bash
# ═══════════════════════════════════════════════════════════
#   Remnasale License — Установка сервера лицензий
# ═══════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DARKGRAY='\033[1;30m'
NC='\033[0m'

_ORIG_STTY=$(stty -g 2>/dev/null || true)
INSTALL_DIR="/opt/remnasale-license"
_spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

cleanup_terminal() {
    [ -n "$_ORIG_STTY" ] && stty "$_ORIG_STTY" 2>/dev/null || true
    tput cnorm 2>/dev/null || true
    printf "\033[0m"
}

_cancel_exit() {
    trap '' INT TERM
    cleanup_terminal
    printf "\r\033[K\n"
    echo -e "${RED}Установка отменена.${NC}"
    echo
    exit 0
}

trap 'cleanup_terminal' EXIT
trap '_cancel_exit' INT TERM

reading_inline() {
    local prompt="$1"
    local var_name="$2"
    local input="" char
    local _rl_stty
    _rl_stty=$(stty -g 2>/dev/null || echo "")
    tput cnorm 2>/dev/null
    echo -en "${BLUE}➜${NC}  ${YELLOW}${prompt}${NC} \033[32m"
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\x08' ]]; then
            if [[ -n "$input" ]]; then
                input="${input%?}"
                echo -en "\b \b"
            fi
        elif [[ "$char" == $'\x1b' ]]; then
            local _seq=""
            while IFS= read -r -s -n1 -t 0.1 _sc; do
                _seq+="$_sc"
                [[ "$_sc" =~ [A-Za-z~] ]] && break
            done
            if [[ -z "$_seq" ]]; then
                echo -en "\033[0m"
                echo
                [ -n "${_rl_stty:-}" ] && stty "$_rl_stty" 2>/dev/null || true
                tput civis 2>/dev/null
                printf -v "$var_name" ''
                return 2
            fi
        else
            input+="$char"
            echo -en "$char"
        fi
    done
    echo -en "\033[0m"
    [ -n "${_rl_stty:-}" ] && stty "$_rl_stty" 2>/dev/null || true
    echo
    tput civis 2>/dev/null
    printf -v "$var_name" '%s' "$input"
    return 0
}

reading_inline_default() {
    local prompt="$1"
    local var_name="$2"
    local default="$3"
    local input="" char
    local _rl_stty
    _rl_stty=$(stty -g 2>/dev/null || echo "")
    tput cnorm 2>/dev/null
    echo -en "${BLUE}➜${NC}  ${YELLOW}${prompt}${NC} ${DARKGRAY}[${default}]${NC}: \033[32m"
    while IFS= read -r -s -n1 char; do
        if [[ -z "$char" ]]; then
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\x08' ]]; then
            if [[ -n "$input" ]]; then
                input="${input%?}"
                echo -en "\b \b"
            fi
        elif [[ "$char" == $'\x1b' ]]; then
            local _seq=""
            while IFS= read -r -s -n1 -t 0.1 _sc; do
                _seq+="$_sc"
                [[ "$_sc" =~ [A-Za-z~] ]] && break
            done
            if [[ -z "$_seq" ]]; then
                echo -en "\033[0m"
                echo
                [ -n "${_rl_stty:-}" ] && stty "$_rl_stty" 2>/dev/null || true
                tput civis 2>/dev/null
                printf -v "$var_name" '%s' "$default"
                return 2
            fi
        else
            input+="$char"
            echo -en "$char"
        fi
    done
    echo -en "\033[0m"
    [ -n "${_rl_stty:-}" ] && stty "$_rl_stty" 2>/dev/null || true
    echo
    tput civis 2>/dev/null
    if [[ -z "$input" ]]; then
        printf -v "$var_name" '%s' "$default"
    else
        printf -v "$var_name" '%s' "$input"
    fi
    return 0
}

_run_spinner() {
    local label="$1"
    shift
    local _tmpfile
    _tmpfile=$(mktemp)
    "$@" >"$_tmpfile" 2>&1 &
    local _pid=$! _si=0
    while kill -0 "$_pid" 2>/dev/null; do
        printf "\r${GREEN}${_spin[$((_si % 10))]}${NC}  %s" "$label"
        _si=$((_si + 1))
        sleep 0.08
    done
    wait "$_pid"
    local _rc=$?
    if [[ $_rc -ne 0 ]]; then
        printf "\r\033[K"
        cat "$_tmpfile"
    fi
    rm -f "$_tmpfile"
    printf "\r\033[K"
    return $_rc
}

# ═══════════════════════════════════════════════════════════

tput civis 2>/dev/null
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo -e "     🔑  Remnasale License — Установка"
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

# Проверка root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}✖  Требуются права root. Запустите с sudo или от root.${NC}"
    exit 1
fi

# Проверка зависимостей
for _cmd in git docker curl; do
    if ! command -v "$_cmd" &>/dev/null; then
        echo -e "${RED}✖  Команда '${_cmd}' не найдена. Установите её и повторите попытку.${NC}"
        exit 1
    fi
done
if ! docker compose version &>/dev/null; then
    echo -e "${RED}✖  Docker Compose не найден. Установите Docker с поддержкой Compose v2.${NC}"
    exit 1
fi

echo -e "${CYAN}Для установки понадобятся:${NC}"
echo -e "  ${DARKGRAY}•${NC} Токен Telegram бота — получить у ${YELLOW}@BotFather${NC}"
echo -e "  ${DARKGRAY}•${NC} Ваш Telegram ID — узнать у ${YELLOW}@userinfobot${NC}"
echo -e "  ${DARKGRAY}•${NC} Домен лиц. сервера ${DARKGRAY}(например: rs-license.dfc-online.com)${NC}"
echo -e "  ${DARKGRAY}•${NC} Домен сайта DFC ${DARKGRAY}(например: dfc-online.com)${NC} — необязательно"
echo
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

# ── BOT_TOKEN ───────────────────────────────────────────────
BOT_TOKEN=""
while [[ -z "$BOT_TOKEN" ]]; do
    reading_inline "Токен Telegram бота:" BOT_TOKEN
    [[ $? -eq 2 ]] && _cancel_exit
    [[ -z "$BOT_TOKEN" ]] && echo -e "${RED}  ✖  Токен не может быть пустым.${NC}"
done
echo

# ── BOT_ADMIN_ID ────────────────────────────────────────────
BOT_ADMIN_ID=""
while [[ -z "$BOT_ADMIN_ID" ]] || ! [[ "$BOT_ADMIN_ID" =~ ^[0-9]+$ ]]; do
    reading_inline "Ваш Telegram ID (числовой):" BOT_ADMIN_ID
    [[ $? -eq 2 ]] && _cancel_exit
    if [[ -z "$BOT_ADMIN_ID" ]] || ! [[ "$BOT_ADMIN_ID" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}  ✖  Введите числовой ID (только цифры).${NC}"
    fi
done
echo

# ── LICENSE_DOMAIN ─────────────────────────────────────────
LICENSE_DOMAIN=""
while [[ -z "$LICENSE_DOMAIN" ]]; do
    reading_inline "Домен лиц. сервера (без https://):" LICENSE_DOMAIN
    [[ $? -eq 2 ]] && _cancel_exit
    LICENSE_DOMAIN=$(echo "$LICENSE_DOMAIN" | sed 's|^https\?://||; s|/.*||')
    [[ -z "$LICENSE_DOMAIN" ]] && echo -e "${RED}  ✖  Домен не может быть пустым.${NC}"
done
echo

# ── SITE_DOMAIN (необязательно) ───────────────────────────
SITE_DOMAIN=""
reading_inline "Домен сайта DFC (Enter — пропустить):" SITE_DOMAIN
if [[ $? -eq 2 ]]; then
    SITE_DOMAIN=""
fi
SITE_DOMAIN=$(echo "$SITE_DOMAIN" | sed 's|^https\?://||; s|/.*||')
echo

API_PORT="8080"

echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

# ── Очистка существующей установки ─────────────────────────
if [[ -d "$INSTALL_DIR" ]]; then
    printf "${GREEN}▶${NC}  Остановка и удаление предыдущей установки...\n"
    docker compose -f "$INSTALL_DIR/docker-compose.yml" down --volumes 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✔${NC}  Предыдущая установка удалена."
fi

# ── Копирование файлов проекта ──────────────────────────────
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${_SCRIPT_DIR}/bot" ]] && [[ -f "${_SCRIPT_DIR}/main.py" ]]; then
    cp -a "${_SCRIPT_DIR}/" "${INSTALL_DIR}/"
else
    echo -e "${RED}✖  Не найдены файлы проекта рядом с install.sh${NC}"
    echo -e "${RED}   Убедитесь, что запускаете install.sh из каталога с проектом.${NC}"
    exit 1
fi
echo -e "${GREEN}✔${NC}  Файлы скопированы."

# ── Создание .env ───────────────────────────────────────────
mkdir -p "$INSTALL_DIR/data"
_SITE_URL=""
[[ -n "$SITE_DOMAIN" ]] && _SITE_URL="https://${SITE_DOMAIN}"
cat > "$INSTALL_DIR/.env" <<EOF
BOT_TOKEN=${BOT_TOKEN}
BOT_ADMIN_ID=${BOT_ADMIN_ID}
API_HOST=0.0.0.0
API_PORT=${API_PORT}
DATABASE_PATH=/data/license.db
PUBLIC_URL=https://${LICENSE_DOMAIN}
LICENSE_SERVER_URL=https://${LICENSE_DOMAIN}
SITE_URL=${_SITE_URL}
EOF
echo -e "${GREEN}✔${NC}  Файл .env создан."
echo

# ── Настройка nginx + SSL ──────────────────────────────────
_setup_nginx() {
    local domain="$1"
    local upstream_port="9777"
    local DIR_NGINX="/opt/nginx/"

    # === Получаем SSL сертификат если нет ===
    if [[ -d "/etc/letsencrypt/live/${domain}" ]]; then
        echo -e "${GREEN}✔${NC}  SSL сертификат уже существует."
    else
        printf "${GREEN}▶${NC}  Получение SSL сертификата...\n"
        # Устанавливаем certbot если нет
        if ! command -v certbot &>/dev/null; then
            apt-get update -qq >/dev/null 2>&1
            apt-get install -y -qq certbot >/dev/null 2>&1
        fi
        # Открываем порт 80 для проверки
        ufw allow 80/tcp >/dev/null 2>&1 || true
        ufw reload >/dev/null 2>&1 || true
        # Останавливаем nginx если запущен (чтобы certbot standalone мог занять :80)
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'remnawave-nginx'; then
            (cd "${DIR_NGINX}" && docker compose stop) >/dev/null 2>&1
            local _nginx_was_running=true
        else
            local _nginx_was_running=false
        fi
        certbot certonly --standalone -d "${domain}" \
            --non-interactive --agree-tos --register-unsafely-without-email \
            --http-01-port 80 --key-type ecdsa >/dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            echo -e "${YELLOW}⚠  Не удалось получить SSL сертификат. Проверьте DNS для ${domain}.${NC}"
            $_nginx_was_running && (cd "${DIR_NGINX}" && docker compose up -d) >/dev/null 2>&1
            return
        fi
        echo -e "${GREEN}✔${NC}  SSL сертификат получен."
        # Восстанавливаем nginx если был запущен
        $_nginx_was_running && (cd "${DIR_NGINX}" && docker compose up -d) >/dev/null 2>&1
    fi

    # === Копируем сертификат в /opt/nginx/ssl/ ===
    local ssl_dst="${DIR_NGINX}ssl/${domain}"
    mkdir -p "$ssl_dst"
    cp -fL "/etc/letsencrypt/live/${domain}/fullchain.pem" "${ssl_dst}/fullchain.pem"
    cp -fL "/etc/letsencrypt/live/${domain}/privkey.pem" "${ssl_dst}/privkey.pem"

    # === Добавляем server-блок в /opt/nginx/nginx.conf ===
    if [[ -f "${DIR_NGINX}nginx.conf" ]]; then
        # Удаляем старый блок LICENSE если есть
        if grep -qF "# BEGIN_LICENSE_BLOCK" "${DIR_NGINX}nginx.conf" 2>/dev/null; then
            local _t; _t=$(mktemp)
            sed '/^# BEGIN_LICENSE_BLOCK/,/^# END_LICENSE_BLOCK/d' "${DIR_NGINX}nginx.conf" > "$_t" && cat "$_t" > "${DIR_NGINX}nginx.conf"
            rm -f "$_t"
        fi
    else
        # Нет nginx.conf — создаём минимальный
        mkdir -p "${DIR_NGINX}" "${DIR_NGINX}ssl"
        cat > "${DIR_NGINX}nginx.conf" <<'MINIMAL_NGINX'
user  nginx;
worker_processes  auto;
error_log  /var/log/nginx/error.log notice;
pid        /run/nginx.pid;

events {
    worker_connections  8192;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    access_log off;
    sendfile on;
    keepalive_timeout 65;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

# ─── Default Direct
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
}
} # ─── end http ───
MINIMAL_NGINX
    fi

    # Вставляем блок перед '} # ─── end http ───'
    local _block
    _block=$(cat <<BLOCK_EOF
# BEGIN_LICENSE_BLOCK
server {
    server_name ${domain};
    listen 443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/${domain}/fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/${domain}/privkey.pem";
    ssl_trusted_certificate "/etc/nginx/ssl/${domain}/fullchain.pem";

    location / {
        proxy_http_version 1.1;
        proxy_pass http://127.0.0.1:${upstream_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
# END_LICENSE_BLOCK
BLOCK_EOF
    )
    local _tmpf; _tmpf=$(mktemp)
    local _bf; _bf=$(mktemp)
    printf '%s\n' "$_block" > "$_bf"
    awk -v blockfile="$_bf" '
        /^} # ─── end http ───/ {
            while ((getline line < blockfile) > 0) print line
            close(blockfile)
        }
        { print }
    ' "${DIR_NGINX}nginx.conf" > "$_tmpf" && cat "$_tmpf" > "${DIR_NGINX}nginx.conf"
    rm -f "$_tmpf" "$_bf"

    # === Создаём docker-compose.yml если нет (автономная установка) ===
    if [[ ! -f "${DIR_NGINX}docker-compose.yml" ]]; then
        cat > "${DIR_NGINX}docker-compose.yml" <<'COMPOSE'
services:
  nginx:
    image: nginx:1.28
    container_name: remnawave-nginx
    hostname: remnawave-nginx
    restart: always
    network_mode: host
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    logging:
      driver: 'json-file'
      options:
        max-size: '30m'
        max-file: '5'
COMPOSE
    fi

    # === Перезапускаем Docker nginx ===
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'remnawave-nginx'; then
        (cd "${DIR_NGINX}" && docker compose up -d >/dev/null 2>&1 && docker exec remnawave-nginx nginx -s reload >/dev/null 2>&1)
    else
        (cd "${DIR_NGINX}" && docker compose up -d >/dev/null 2>&1)
    fi

    echo -e "${GREEN}✔${NC}  Nginx настроен для ${YELLOW}${domain}${NC}."

    # === Cron для обновления сертификатов ===
    local _deploy_hook='for d in /opt/nginx/ssl/*/; do dn=$(basename "$d"); src="/etc/letsencrypt/live/$dn"; [ -f "$src/fullchain.pem" ] && cp -fL "$src/fullchain.pem" "$d/fullchain.pem" && cp -fL "$src/privkey.pem" "$d/privkey.pem"; done; cd /opt/nginx 2>/dev/null && docker compose restart nginx 2>/dev/null'
    if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook '${_deploy_hook}' 2>/dev/null") | crontab -
    fi
}

_setup_nginx "$LICENSE_DOMAIN"
echo

# ── Настройка сайта DFC (опционально) ──────────────────────
_setup_site() {
    local domain="$1"
    local DIR_NGINX="/opt/nginx/"
    local SITE_DIR="$INSTALL_DIR/site"

    echo -e "${GREEN}▶${NC}  Настройка сайта DFC на ${YELLOW}${domain}${NC}..."

    # === SSL через ACME ===
    if [[ -d "/etc/letsencrypt/live/${domain}" ]]; then
        echo -e "${GREEN}✔${NC}  SSL сертификат для ${domain} уже существует."
    else
        printf "${GREEN}▶${NC}  Получение SSL сертификата для ${domain}...\n"
        if ! command -v certbot &>/dev/null; then
            apt-get update -qq >/dev/null 2>&1
            apt-get install -y -qq certbot >/dev/null 2>&1
        fi
        ufw allow 80/tcp >/dev/null 2>&1 || true
        ufw reload >/dev/null 2>&1 || true
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'remnawave-nginx'; then
            (cd "${DIR_NGINX}" && docker compose stop) >/dev/null 2>&1
            local _nginx_was_running=true
        else
            local _nginx_was_running=false
        fi
        certbot certonly --standalone -d "${domain}" \
            --non-interactive --agree-tos --register-unsafely-without-email \
            --http-01-port 80 --key-type ecdsa >/dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            echo -e "${YELLOW}⚠  Не удалось получить SSL для ${domain}. Проверьте DNS.${NC}"
            $_nginx_was_running && (cd "${DIR_NGINX}" && docker compose up -d) >/dev/null 2>&1
            return
        fi
        echo -e "${GREEN}✔${NC}  SSL сертификат для ${domain} получен."
        $_nginx_was_running && (cd "${DIR_NGINX}" && docker compose up -d) >/dev/null 2>&1
    fi

    # === Копируем сертификат ===
    local ssl_dst="${DIR_NGINX}ssl/${domain}"
    mkdir -p "$ssl_dst"
    cp -fL "/etc/letsencrypt/live/${domain}/fullchain.pem" "${ssl_dst}/fullchain.pem"
    cp -fL "/etc/letsencrypt/live/${domain}/privkey.pem" "${ssl_dst}/privkey.pem"

    # === Добавляем volume для сайта в docker-compose nginx ===
    if [[ -f "${DIR_NGINX}docker-compose.yml" ]]; then
        if ! grep -q "/var/www/dfc-site" "${DIR_NGINX}docker-compose.yml" 2>/dev/null; then
            sed -i "/\/var\/www\/html.*:ro/a\\      - ${SITE_DIR}:/var/www/dfc-site:ro" "${DIR_NGINX}docker-compose.yml" 2>/dev/null || true
        fi
    fi

    # === Удаляем старые блоки ABOUT/SITE ===
    if [[ -f "${DIR_NGINX}nginx.conf" ]]; then
        local _t; _t=$(mktemp)
        sed '/^# BEGIN_ABOUT_BLOCK/,/^# END_ABOUT_BLOCK/d; /^# BEGIN_SITE_BLOCK/,/^# END_SITE_BLOCK/d' "${DIR_NGINX}nginx.conf" > "$_t" && cat "$_t" > "${DIR_NGINX}nginx.conf"
        rm -f "$_t"
    fi

    # === Вставляем server-блок для сайта ===
    local _block
    _block=$(cat <<BLOCK_EOF
# BEGIN_SITE_BLOCK
server {
    server_name ${domain};
    listen 443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/${domain}/fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/${domain}/privkey.pem";
    ssl_trusted_certificate "/etc/nginx/ssl/${domain}/fullchain.pem";

    root /var/www/dfc-site;
    index index.html;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }
}
# END_SITE_BLOCK
BLOCK_EOF
    )
    local _tmpf; _tmpf=$(mktemp)
    local _bf; _bf=$(mktemp)
    printf '%s\n' "$_block" > "$_bf"
    awk -v blockfile="$_bf" '
        /^} # ─── end http ───/ {
            while ((getline line < blockfile) > 0) print line
            close(blockfile)
        }
        { print }
    ' "${DIR_NGINX}nginx.conf" > "$_tmpf" && cat "$_tmpf" > "${DIR_NGINX}nginx.conf"
    rm -f "$_tmpf" "$_bf"

    # === Перезапуск nginx ===
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'remnawave-nginx'; then
        (cd "${DIR_NGINX}" && docker compose up -d >/dev/null 2>&1 && docker exec remnawave-nginx nginx -s reload >/dev/null 2>&1)
    fi

    echo -e "${GREEN}✔${NC}  Сайт DFC настроен: ${YELLOW}https://${domain}${NC}"
}

if [[ -n "$SITE_DOMAIN" ]]; then
    _setup_site "$SITE_DOMAIN"
    echo
fi

# ── Открытие портов в ufw ──────────────────────────────────
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    ufw reload >/dev/null 2>&1 || true
    echo -e "${GREEN}✔${NC}  Порты ${YELLOW}80, 443${NC} открыты в ufw."
fi

# ── Сборка и запуск контейнеров ────────────────────────────
# Копируем сайт DFC если есть about-page рядом с проектом
if [[ -d "${_SCRIPT_DIR}/../about-page" ]]; then
    mkdir -p "$INSTALL_DIR/site"
    cp -a "${_SCRIPT_DIR}/../about-page/." "$INSTALL_DIR/site/"
    echo -e "${GREEN}✔${NC}  Файлы сайта DFC скопированы."
fi

printf "${GREEN}▶${NC}  Сборка и запуск контейнеров...\n"
docker compose -f "$INSTALL_DIR/docker-compose.yml" up -d --build
if [[ $? -ne 0 ]]; then
    echo -e "${RED}✖  Ошибка запуска контейнеров. Проверьте вывод выше.${NC}"
    exit 1
fi
echo -e "${GREEN}✔${NC}  Контейнер запущен."

# ── Установка команды rl ────────────────────────────────────
chmod +x "$INSTALL_DIR/rl.sh"
ln -sf "$INSTALL_DIR/rl.sh" /usr/local/bin/rl
echo -e "${GREEN}✔${NC}  Команда ${YELLOW}rl${NC} установлена."
echo

echo -e "${BLUE}══════════════════════════════════════${NC}"
echo -e "${GREEN}✅  Установка завершена!${NC}"
echo
echo -e "  ${CYAN}Домен сервера лицензий:${NC}"
echo -e "  ${YELLOW}https://${LICENSE_DOMAIN}${NC}"
if [[ -n "$SITE_DOMAIN" ]]; then
    echo
    echo -e "  ${CYAN}Сайт DFC Project:${NC}"
    echo -e "  ${YELLOW}https://${SITE_DOMAIN}${NC}"
fi
echo
echo -e "  ${DARKGRAY}Укажите этот домен в настройках установки клиентов:${NC}"
echo -e "  ${DARKGRAY}LICENSE_SERVER=\"https://${LICENSE_DOMAIN}\"${NC}"
echo
echo -e "  ${CYAN}Управление:${NC} напишите боту ${YELLOW}/start${NC}"
echo -e "  ${CYAN}Консоль:${NC}    команда ${YELLOW}rl${NC}"
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

tput cnorm 2>/dev/null
