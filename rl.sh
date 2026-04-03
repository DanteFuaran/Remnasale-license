#!/bin/bash
# ═══════════════════════════════════════════════
#   rl — Управление Remnasale License сервером
# ═══════════════════════════════════════════════

set -euo pipefail

# ─── Цвета ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
WHITE='\033[1;37m'
GRAY='\033[0;37m'
DARKGRAY='\033[1;30m'
NC='\033[0m'

COMPOSE_DIR="/opt/remnasale-license"
CONTAINER_NAME="remnasale-license"

_flush_stdin() {
    local _dummy
    while IFS= read -rsn1 -t 0 _dummy 2>/dev/null; do true; done
    true
}

_service_status() {
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
        echo "running"
    else
        echo "stopped"
    fi
}

show_spinner() {
    local pid=$!
    local delay=0.08
    local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0 msg="$1" done_msg="${2:-$1}"
    tput civis 2>/dev/null || true
    while kill -0 $pid 2>/dev/null; do
        printf "\r${GREEN}%s${NC}  %b" "${spin[$i]}" "$msg"
        i=$(( (i+1) % 10 ))
        sleep $delay
    done
    local exit_code=0
    wait $pid 2>/dev/null || exit_code=$?
    if [ $exit_code -eq 0 ]; then
        printf "\r\033[K${GREEN}✅${NC} %b\n" "$done_msg"
    else
        printf "\r\033[K${RED}✖${NC} %b\n" "$done_msg"
    fi
    tput cnorm 2>/dev/null || true
    return $exit_code
}

show_arrow_menu() {
    set +e
    local title="$1"
    shift
    local options=("$@")
    local num_options=${#options[@]}
    local selected=0

    if ! [ -t 0 ]; then
        return 255
    fi

    local original_stty=""
    original_stty=$(stty -g 2>/dev/null || echo "")

    tput civis 2>/dev/null || true
    stty -icanon -echo isig min 1 time 0 2>/dev/null || true

    _restore_stty() {
        if [ -n "${original_stty:-}" ]; then
            stty "$original_stty" 2>/dev/null || stty sane 2>/dev/null || true
        else
            stty sane 2>/dev/null || true
        fi
    }
    _restore_term() {
        _restore_stty
        tput cnorm 2>/dev/null || true
    }

    trap "_restore_stty" RETURN

    _flush_stdin

    while [[ "${options[$selected]}" =~ ^[─━═[:space:]]*$ ]]; do
        ((selected++))
        [ $selected -ge $num_options ] && selected=0
    done

    while true; do
        clear
        echo -e "${BLUE}══════════════════════════════════════${NC}"
        if [[ "$title" == *\\n* ]]; then
            local _first="${title%%\\n*}"
            local _rest="${title#*\\n}"
            local _clean
            _clean=$(echo -e "$_first" | sed 's/\x1b\[[0-9;]*m//g')
            local _vlen=${#_clean}
            local _pad=$(( (38 - _vlen) / 2 ))
            [ $_pad -lt 0 ] && _pad=0
            printf "%${_pad}s" ""
            echo -e "${GREEN}${_first}${NC}"
            echo -e "${_rest}"
        else
            local _clean
            _clean=$(echo -e "$title" | sed 's/\x1b\[[0-9;]*m//g')
            local _vlen=${#_clean}
            local _pad=$(( (38 - _vlen) / 2 ))
            [ $_pad -lt 0 ] && _pad=0
            printf "%${_pad}s" ""
            echo -e "${GREEN}$title${NC}"
        fi
        echo -e "${BLUE}══════════════════════════════════════${NC}"
        echo

        for i in "${!options[@]}"; do
            if [[ "${options[$i]}" =~ ^[─━═[:space:]]*$ ]]; then
                echo -e "${DARKGRAY}${options[$i]}${NC}"
            elif [ $i -eq $selected ]; then
                echo -e "${BLUE}▶${NC} ${YELLOW}${options[$i]}${NC}"
            else
                echo -e "  ${options[$i]}"
            fi
        done

        echo
        echo -e "${BLUE}══════════════════════════════════════${NC}"
        local _esc_label="${MENU_ESC_LABEL:-Выход}"
        echo -e "${DARKGRAY}${BLUE}↑↓${DARKGRAY}: Навигация  ${BLUE}Enter${DARKGRAY}: Выбор  ${BLUE}Esc${DARKGRAY}: ${_esc_label}${NC}"
        echo

        local key
        read -rsn1 key 2>/dev/null || key=""

        if [[ "$key" == $'\e' ]]; then
            local seq1="" seq2=""
            read -rsn1 -t 0.1 seq1 2>/dev/null || seq1=""
            if [[ "$seq1" == '[' ]]; then
                read -rsn1 -t 0.1 seq2 2>/dev/null || seq2=""
                case "$seq2" in
                    'A')
                        ((selected--))
                        [ $selected -lt 0 ] && selected=$((num_options - 1))
                        while [[ "${options[$selected]}" =~ ^[─━═[:space:]]*$ ]]; do
                            ((selected--))
                            [ $selected -lt 0 ] && selected=$((num_options - 1))
                        done
                        ;;
                    'B')
                        ((selected++))
                        [ $selected -ge $num_options ] && selected=0
                        while [[ "${options[$selected]}" =~ ^[─━═[:space:]]*$ ]]; do
                            ((selected++))
                            [ $selected -ge $num_options ] && selected=0
                        done
                        ;;
                esac
            else
                _restore_term
                return 255
            fi
        else
            local key_code
            if [ -n "$key" ]; then
                key_code=$(printf '%d' "'$key" 2>/dev/null || echo 0)
            else
                key_code=13
            fi
            if [ "$key_code" -eq 10 ] || [ "$key_code" -eq 13 ]; then
                _restore_stty
                tput civis 2>/dev/null || true
                return $selected
            fi
        fi
    done
}

do_restart() {
    clear
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}       🔄  Перезапуск сервера${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo
    cd "$COMPOSE_DIR" || { echo -e "${RED}✖ Папка $COMPOSE_DIR не найдена${NC}"; return; }
    ( docker compose restart >/dev/null 2>&1 ) &
    show_spinner "Перезапуск контейнера" "Контейнер перезапущен"
    echo
    echo -e "${DARKGRAY}Нажмите Enter для продолжения...${NC}"
    read -r
}

do_start() {
    clear
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}        ▶️   Запуск сервера${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo
    cd "$COMPOSE_DIR" || { echo -e "${RED}✖ Папка $COMPOSE_DIR не найдена${NC}"; return; }
    ( docker compose up -d >/dev/null 2>&1 ) &
    show_spinner "Запуск контейнера" "Контейнер запущен"
    echo
    echo -e "${DARKGRAY}Нажмите Enter для продолжения...${NC}"
    read -r
}

do_stop() {
    clear
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}       ⏹️   Остановка сервера${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo
    cd "$COMPOSE_DIR" || { echo -e "${RED}✖ Папка $COMPOSE_DIR не найдена${NC}"; return; }
    ( docker compose stop >/dev/null 2>&1 ) &
    show_spinner "Остановка контейнера" "Контейнер остановлен"
    echo
    echo -e "${DARKGRAY}Нажмите Enter для продолжения...${NC}"
    read -r
}

do_logs() {
    clear
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}        📜  Логи сервера${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${DARKGRAY}Ctrl+C для выхода${NC}"
    echo
    set +e
    docker logs -f "$CONTAINER_NAME" --tail 50 2>&1 || true
    set -e
    echo
}

do_update() {
    clear
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}       🔁  Обновление сервера${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo

    local REPO_URL="https://github.com/DanteFuaran/Remnasale-license.git"
    local TMP_DIR
    TMP_DIR=$(mktemp -d)

    (
        git clone --depth=1 "$REPO_URL" "$TMP_DIR" >/dev/null 2>&1
    ) &
    show_spinner "Загрузка обновления с GitHub" "Репозиторий скачан"

    if [ ! -f "$TMP_DIR/Dockerfile" ]; then
        echo -e "${RED}✖ Не удалось скачать репозиторий${NC}"
        rm -rf "$TMP_DIR"
        echo -e "${DARKGRAY}Нажмите Enter для продолжения...${NC}"
        read -r
        return
    fi

    # Сборка нового образа
    (
        cd "$TMP_DIR"
        DOCKER_BUILDKIT=1 docker build -t remnasale-license:local . >/dev/null 2>&1
    ) &
    show_spinner "Сборка образа" "Образ собран"

    # Обновляем файлы (кроме .env и data/)
    (
        for f in api.py bot config.py database.py main.py requirements.txt Dockerfile docker-compose.yml version; do
            [ -e "$TMP_DIR/$f" ] && cp -rf "$TMP_DIR/$f" "$COMPOSE_DIR/$f" 2>/dev/null || true
        done
        # Обновляем rl.sh и устанавливаем в /usr/local/bin
        if [ -f "$TMP_DIR/rl.sh" ]; then
            cp -f "$TMP_DIR/rl.sh" "$COMPOSE_DIR/rl.sh"
            chmod +x "$COMPOSE_DIR/rl.sh"
            cp -f "$TMP_DIR/rl.sh" /usr/local/bin/rl
            chmod +x /usr/local/bin/rl
        fi
    ) &
    show_spinner "Обновление файлов" "Файлы обновлены"

    # Перезапускаем контейнер с новым образом
    (
        cd "$COMPOSE_DIR"
        docker compose up -d --force-recreate >/dev/null 2>&1
    ) &
    show_spinner "Перезапуск контейнера" "Сервер обновлён"

    rm -rf "$TMP_DIR"

    local NEW_VER
    NEW_VER=$(grep '^version:' "$COMPOSE_DIR/version" 2>/dev/null | awk '{print $2}' | tr -d '\n' || echo "?")
    echo
    echo -e "${GREEN}✅ Обновление завершено — версия: ${WHITE}v${NEW_VER}${NC}"
    echo
    echo -e "${DARKGRAY}Нажмите Enter для продолжения...${NC}"
    read -r
}

do_delete() {
    local -a del_items=(
        "❌  Отмена"
        "──────────────────────────────────────"
        "🗑️   Да, удалить всё"
    )
    MENU_ESC_LABEL="Отмена"
    show_arrow_menu "🗑️  Удалить license-сервер?\n\n${YELLOW}⚠️  Будут удалены:${NC}\n${DARKGRAY}  • Контейнер и образ\n  • Папка ${WHITE}$COMPOSE_DIR${DARKGRAY}\n  • Команда ${WHITE}rl${NC}" \
        "${del_items[@]}"
    local choice=$?
    unset MENU_ESC_LABEL

    if [ "$choice" -eq 2 ]; then
        clear
        echo -e "${BLUE}══════════════════════════════════════${NC}"
        echo -e "${GREEN}     🗑️   Удаление license-сервера${NC}"
        echo -e "${BLUE}══════════════════════════════════════${NC}"
        echo
        if [ -d "$COMPOSE_DIR" ]; then
            cd "$COMPOSE_DIR" || true
            ( docker compose down --rmi all -v 2>/dev/null || docker compose down 2>/dev/null ) &
            show_spinner "Удаление контейнера и образа" "Контейнер удалён"
        fi
        ( rm -rf "$COMPOSE_DIR" ) &
        show_spinner "Удаление файлов $COMPOSE_DIR" "Файлы удалены"
        rm -f /usr/local/bin/rl
        echo
        echo -e "${GREEN}✅ License-сервер полностью удалён${NC}"
        echo
        echo -e "${DARKGRAY}Нажмите Enter для выхода...${NC}"
        read -r
        clear
        exit 0
    fi
}

_get_local_version() {
    grep '^version:' "$COMPOSE_DIR/version" 2>/dev/null | awk '{print $2}' | tr -d '\n' || echo ""
}

_get_remote_version() {
    curl -sf --max-time 5 \
        "https://raw.githubusercontent.com/DanteFuaran/Remnasale-license/main/version" \
        2>/dev/null | grep '^version:' | awk '{print $2}' | tr -d '\n' || echo ""
}

_version_gt() {
    # returns 0 if $1 > $2
    local a="$1" b="$2"
    [ "$(printf '%s\n%s' "$a" "$b" | sort -V | tail -1)" = "$a" ] && [ "$a" != "$b" ]
}

main_menu() {
    if ! [ -t 0 ]; then
        exit 0
    fi

    # Проверяем версию один раз при входе в меню
    local _LOCAL_VER _REMOTE_VER _UPDATE_AVAILABLE
    _LOCAL_VER=$(_get_local_version)
    _REMOTE_VER=$(_get_remote_version)
    if [ -n "$_REMOTE_VER" ] && _version_gt "$_REMOTE_VER" "$_LOCAL_VER"; then
        _UPDATE_AVAILABLE=1
    else
        _UPDATE_AVAILABLE=0
    fi

    while true; do
        local status
        status=$(_service_status)
        local status_dot status_text
        if [ "$status" = "running" ]; then
            status_dot="${GREEN}●${NC}"
            status_text="${GREEN}Работает${NC}"
        else
            status_dot="${RED}●${NC}"
            status_text="${RED}Остановлен${NC}"
        fi

        local _ver_label=""
        [ -n "$_LOCAL_VER" ] && _ver_label=" v${_LOCAL_VER}"
        local menu_title="⚖️  Remnasale License${_ver_label}\n   Статус: ${status_dot} ${status_text}"

        local update_label="🔁  Обновить"
        if [ "$_UPDATE_AVAILABLE" -eq 1 ]; then
            update_label="🔁  Обновить ${YELLOW}(Доступно обновление до v${_REMOTE_VER})${NC}"
        fi

        local -a items=(
            "🔄  Перезапустить"
            "▶️   Запустить"
            "⏹️   Остановить"
            "📜  Логи"
            "$update_label"
            "──────────────────────────────────────"
            "🗑️   Удалить"
            "──────────────────────────────────────"
            "❌  Выход"
        )

        MENU_ESC_LABEL="Выход"
        show_arrow_menu "$menu_title" "${items[@]}"
        local choice=$?
        unset MENU_ESC_LABEL

        case $choice in
            0) do_restart ;;
            1) do_start ;;
            2) do_stop ;;
            3) do_logs ;;
            4)
                do_update
                # После обновления пересчитываем версии
                _LOCAL_VER=$(_get_local_version)
                _REMOTE_VER=$(_get_remote_version)
                if [ -n "$_REMOTE_VER" ] && _version_gt "$_REMOTE_VER" "$_LOCAL_VER"; then
                    _UPDATE_AVAILABLE=1
                else
                    _UPDATE_AVAILABLE=0
                fi
                ;;
            6) do_delete ;;
            8|255) clear; exit 0 ;;
        esac
    done
}

main_menu
