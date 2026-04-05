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
REPO_URL="https://github.com/DanteFuaran/Remnasale-license.git"
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
echo -e "  ${DARKGRAY}•${NC} GitHub PAT с доступом к Remnasale ${DARKGRAY}(scope: repo)${NC}"
echo -e "  ${DARKGRAY}•${NC} Домен этого сервера ${DARKGRAY}(например: rs-license.dfc-online.com)${NC}"
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

# ── GITHUB_PAT ──────────────────────────────────────────────
GITHUB_PAT=""
while [[ -z "$GITHUB_PAT" ]]; do
    reading_inline "GitHub PAT (scope: repo):" GITHUB_PAT
    [[ $? -eq 2 ]] && _cancel_exit
    [[ -z "$GITHUB_PAT" ]] && echo -e "${RED}  ✖  PAT не может быть пустым.${NC}"
done
echo

# ── LICENSE_DOMAIN ─────────────────────────────────────────
LICENSE_DOMAIN=""
while [[ -z "$LICENSE_DOMAIN" ]]; do
    reading_inline "Домен этого сервера (без https://)" LICENSE_DOMAIN
    [[ $? -eq 2 ]] && _cancel_exit
    LICENSE_DOMAIN=$(echo "$LICENSE_DOMAIN" | sed 's|^https\?://||; s|/.*||')
    [[ -z "$LICENSE_DOMAIN" ]] && echo -e "${RED}  ✖  Домен не может быть пустым.${NC}"
done
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

# ── Клонирование репозитория ────────────────────────────────
_run_spinner "Клонирование license-сервера" env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="" git -c credential.helper="" clone "$REPO_URL" "$INSTALL_DIR"
if [[ $? -ne 0 ]]; then
    echo -e "${RED}✖  Ошибка клонирования. Проверьте интернет-соединение.${NC}"
    exit 1
fi
echo -e "${GREEN}✔${NC}  Репозиторий клонирован."

# ── Создание .env ───────────────────────────────────────────
mkdir -p "$INSTALL_DIR/data"
cat > "$INSTALL_DIR/.env" <<EOF
BOT_TOKEN=${BOT_TOKEN}
BOT_ADMIN_ID=${BOT_ADMIN_ID}
API_HOST=0.0.0.0
API_PORT=${API_PORT}
DATABASE_PATH=/data/license.db
GITHUB_PAT=${GITHUB_PAT}
GITHUB_REPO=DanteFuaran/Remnasale
PUBLIC_URL=https://${LICENSE_DOMAIN}
EOF
echo -e "${GREEN}✔${NC}  Файл .env создан."
echo

# ── Установка nginx + SSL ──────────────────────────────────
_setup_nginx() {
    local domain="$1"
    local upstream_port="9777"

    # Устанавливаем nginx если нет
    if ! command -v nginx &>/dev/null; then
        printf "${GREEN}▶${NC}  Установка nginx...\n"
        apt-get update -qq >/dev/null 2>&1
        apt-get install -y -qq nginx >/dev/null 2>&1
        systemctl enable nginx >/dev/null 2>&1
        echo -e "${GREEN}✔${NC}  Nginx установлен."
    else
        echo -e "${GREEN}✔${NC}  Nginx уже установлен."
    fi

    # Устанавливаем certbot если нет
    if ! command -v certbot &>/dev/null; then
        printf "${GREEN}▶${NC}  Установка certbot...\n"
        apt-get install -y -qq certbot python3-certbot-nginx >/dev/null 2>&1
        echo -e "${GREEN}✔${NC}  Certbot установлен."
    fi

    local NGINX_CONF="/etc/nginx/sites-available/${domain}"
    local NGINX_LINK="/etc/nginx/sites-enabled/${domain}"

    # Создаём конфиг nginx (HTTP для получения сертификата)
    cat > "$NGINX_CONF" <<NGINX_EOF
server {
    listen 80;
    server_name ${domain};

    location / {
        proxy_pass http://127.0.0.1:${upstream_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_send_timeout 300;
    }
}
NGINX_EOF

    # Активируем конфиг
    ln -sf "$NGINX_CONF" "$NGINX_LINK" 2>/dev/null
    # Удаляем default если мешает
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null

    # Проверяем и перезапускаем nginx
    nginx -t >/dev/null 2>&1 && systemctl restart nginx >/dev/null 2>&1

    # Получаем/обновляем SSL сертификат
    if [[ -d "/etc/letsencrypt/live/${domain}" ]]; then
        echo -e "${GREEN}✔${NC}  SSL сертификат уже существует."
    else
        printf "${GREEN}▶${NC}  Получение SSL сертификата...\n"
        certbot --nginx -d "${domain}" --non-interactive --agree-tos --register-unsafely-without-email >/dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            echo -e "${YELLOW}⚠  Не удалось получить SSL сертификат. Проверьте DNS для ${domain}.${NC}"
            return
        fi
        echo -e "${GREEN}✔${NC}  SSL сертификат получен."
    fi

    # Обновляем конфиг для HTTPS
    cat > "$NGINX_CONF" <<NGINX_EOF
server {
    listen 80;
    server_name ${domain};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${domain};

    ssl_certificate /etc/letsencrypt/live/${domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${domain}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:${upstream_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_send_timeout 300;
    }
}
NGINX_EOF

    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1
    echo -e "${GREEN}✔${NC}  Nginx настроен для ${YELLOW}${domain}${NC}."
}

_setup_nginx "$LICENSE_DOMAIN"
echo

# ── Открытие портов в ufw ──────────────────────────────────
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    ufw reload >/dev/null 2>&1 || true
    echo -e "${GREEN}✔${NC}  Порты ${YELLOW}80, 443${NC} открыты в ufw."
fi

# ── Сборка и запуск контейнеров ────────────────────────────
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
echo
echo -e "  ${DARKGRAY}Укажите этот домен в настройках установки клиентов:${NC}"
echo -e "  ${DARKGRAY}LICENSE_SERVER=\"https://${LICENSE_DOMAIN}\"${NC}"
echo
echo -e "  ${CYAN}Управление:${NC} напишите боту ${YELLOW}/start${NC}"
echo -e "  ${CYAN}Консоль:${NC}    команда ${YELLOW}rl${NC}"
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

tput cnorm 2>/dev/null
