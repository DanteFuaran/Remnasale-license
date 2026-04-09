#!/bin/bash
# ═══════════════════════════════════════════════════════════
#   DFC Manager — Скрипт установки
#   Запуск: bash <(curl -sL https://rs-license.dfc-online.com/api/v1/manager/install)
# ═══════════════════════════════════════════════════════════

set -euo pipefail

_BLUE='\033[1;34m'
_GREEN='\033[0;32m'
_RED='\033[0;31m'
_YELLOW='\033[1;33m'
_NC='\033[0m'

_INSTALL_DIR="/usr/local/dfc-manager"
_DFC_SERVER="https://rs-license.dfc-online.com"

echo -e "${_BLUE}══════════════════════════════════════${_NC}"
echo -e "${_GREEN}      🛠️  Установка DFC Manager${_NC}"
echo -e "${_BLUE}══════════════════════════════════════${_NC}"
echo

# ─── Проверка root ────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${_RED}✖ Скрипт нужно запускать от root${_NC}"
    exit 1
fi

# ─── Проверка curl ────────────────────────────────────────
if ! command -v curl &>/dev/null; then
    echo -e "${_YELLOW}⚠ curl не найден, устанавливаю...${_NC}"
    apt-get update -qq && apt-get install -y -qq curl >/dev/null 2>&1 || {
        echo -e "${_RED}✖ Не удалось установить curl${_NC}"
        exit 1
    }
fi

# ─── Проверка tar ─────────────────────────────────────────
if ! command -v tar &>/dev/null; then
    echo -e "${_YELLOW}⚠ tar не найден, устанавливаю...${_NC}"
    apt-get update -qq && apt-get install -y -qq tar >/dev/null 2>&1 || {
        echo -e "${_RED}✖ Не удалось установить tar${_NC}"
        exit 1
    }
fi

# ─── Обработка прерывания ─────────────────────────────────
trap 'stty sane 2>/dev/null; tput cnorm 2>/dev/null; echo -e "\n${_RED}Установка прервана${_NC}"; exit 130' INT TERM

cd /opt >/dev/null 2>&1 || true
mkdir -p /usr/local/bin || { echo -e "${_RED}✖ Ошибка создания /usr/local/bin${_NC}"; exit 1; }

# ─── Проверка уже установленного ──────────────────────────
if [ -f "${_INSTALL_DIR}/dfc-manager.sh" ] && [ -d "${_INSTALL_DIR}/lib" ]; then
    echo -e "${_GREEN}✅ DFC Manager уже установлен${_NC}"
    echo -e "   Запуск: ${_BLUE}dfc${_NC} или ${_BLUE}rw${_NC}"
    echo
    exec "${_INSTALL_DIR}/dfc-manager.sh" "$@"
fi

# ─── Загрузка и установка ─────────────────────────────────
rm -rf "${_INSTALL_DIR}"
mkdir -p "${_INSTALL_DIR}"

echo -ne "  ${_BLUE}⬇ Загрузка DFC Manager...${_NC}"
if ! curl -sL --max-time 120 --connect-timeout 15 \
        "${_DFC_SERVER}/api/v1/manager/download" \
        | tar -xz -C "${_INSTALL_DIR}" --strip-components=1 2>/dev/null; then
    echo -e "\r  ${_RED}✖ Не удалось загрузить DFC Manager${_NC}                "
    echo -e "  ${_RED}Проверьте соединение с интернетом${_NC}"
    rm -rf "${_INSTALL_DIR}"
    exit 1
fi
echo -e "\r  ${_GREEN}✅ DFC Manager загружен${_NC}                         "

chmod +x "${_INSTALL_DIR}/dfc-manager.sh"

# ─── Создание симлинков ───────────────────────────────────
ln -sf "${_INSTALL_DIR}/dfc-manager.sh" /usr/local/bin/dfc-manager
ln -sf /usr/local/bin/dfc-manager /usr/local/bin/dfc
ln -sf /usr/local/bin/dfc-manager /usr/local/bin/rw

echo -e "${_GREEN}✅ Установка завершена!${_NC}"
echo
echo -e "  Команды: ${_BLUE}dfc${_NC}  или  ${_BLUE}rw${_NC}"
echo

# ─── Запуск ───────────────────────────────────────────────
exec "${_INSTALL_DIR}/dfc-manager.sh" "$@"
