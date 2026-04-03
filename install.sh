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
SETUP_DIR="/opt/remnasale-setup"
REPO_URL="https://github.com/DanteFuaran/Remnasale-license.git"
SETUP_REPO_URL="https://github.com/DanteFuaran/Remnasale.git"
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

# Автоопределение IP сервера
SERVER_IP=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
            curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
            hostname -I 2>/dev/null | awk '{print $1}')

echo -e "${CYAN}Для установки понадобятся:${NC}"
echo -e "  ${DARKGRAY}•${NC} Токен Telegram бота — получить у ${YELLOW}@BotFather${NC}"
echo -e "  ${DARKGRAY}•${NC} Ваш Telegram ID — узнать у ${YELLOW}@userinfobot${NC}"
echo -e "  ${DARKGRAY}•${NC} GitHub PAT с доступом к Remnasale ${DARKGRAY}(scope: repo)${NC}"
echo
if [[ -n "$SERVER_IP" ]]; then
    echo -e "  ${DARKGRAY}•${NC} IP этого сервера: ${GREEN}${SERVER_IP}${NC} ${DARKGRAY}(определён автоматически)${NC}"
fi
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

# ── API_PORT ────────────────────────────────────────────────
API_PORT=""
reading_inline_default "Порт API:" API_PORT "8080"
[[ $? -eq 2 ]] && _cancel_exit
if ! [[ "$API_PORT" =~ ^[0-9]+$ ]] || [[ "$API_PORT" -lt 1 ]] || [[ "$API_PORT" -gt 65535 ]]; then
    echo -e "${YELLOW}  ⚠  Некорректный порт, используется 8080.${NC}"
    API_PORT="8080"
fi
echo

echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

# ── Клонирование / обновление репозитория ──────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
    printf "${GREEN}▶${NC}  Обновление существующей установки...\n"
    _run_spinner "Обновление репозитория" env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="" git -c credential.helper="" -C "$INSTALL_DIR" pull origin main
    if [[ $? -ne 0 ]]; then
        echo -e "${RED}✖  Ошибка обновления репозитория.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✔${NC}  Репозиторий обновлён."
else
    _run_spinner "Клонирование license-сервера" env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="" git -c credential.helper="" clone "$REPO_URL" "$INSTALL_DIR"
    if [[ $? -ne 0 ]]; then
        echo -e "${RED}✖  Ошибка клонирования. Проверьте интернет-соединение.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✔${NC}  Репозиторий клонирован."
fi

# ── Клонирование / обновление setup-файлов ─────────────────
SETUP_REPO_AUTH="https://${GITHUB_PAT}@github.com/DanteFuaran/Remnasale.git"
if [[ -d "$SETUP_DIR/.git" ]]; then
    _run_spinner "Обновление setup-файлов" env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="" git -c credential.helper="" -C "$SETUP_DIR" pull "$SETUP_REPO_AUTH" lic
    if [[ $? -ne 0 ]]; then
        echo -e "${YELLOW}  ⚠  Не удалось обновить setup-файлы, продолжаем...${NC}"
    else
        echo -e "${GREEN}✔${NC}  Setup-файлы обновлены."
    fi
else
    _run_spinner "Загрузка setup-файлов" env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="" git -c credential.helper="" clone --branch lic --single-branch "$SETUP_REPO_AUTH" "$SETUP_DIR"
    if [[ $? -ne 0 ]]; then
        echo -e "${YELLOW}  ⚠  Не удалось загрузить setup-файлы (проверьте PAT). Продолжаем...${NC}"
    else
        echo -e "${GREEN}✔${NC}  Setup-файлы загружены."
    fi
fi

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
SETUP_DIR=/setup
EOF
echo -e "${GREEN}✔${NC}  Файл .env создан."
echo

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
if [[ -n "$SERVER_IP" ]]; then
    echo -e "  ${CYAN}IP сервера лицензий:${NC}"
    echo -e "  ${YELLOW}${SERVER_IP}:${API_PORT}${NC}"
    echo
    echo -e "  ${DARKGRAY}Укажите этот адрес в настройках установки клиентов:${NC}"
    echo -e "  ${DARKGRAY}LICENSE_SERVER=\"http://${SERVER_IP}:${API_PORT}\"${NC}"
    echo
fi
echo -e "  ${CYAN}Управление:${NC} напишите боту ${YELLOW}/start${NC}"
echo -e "  ${CYAN}Консоль:${NC}    команда ${YELLOW}rl${NC}"
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo

tput cnorm 2>/dev/null
