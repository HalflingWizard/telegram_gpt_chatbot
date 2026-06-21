#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE="${CONFIG_FILE:-config.env}"
CONFIG_TEMPLATE="${CONFIG_TEMPLATE:-config.env.example}"
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
    echo "Created $CONFIG_FILE from $CONFIG_TEMPLATE."
    echo "Edit $CONFIG_FILE and then run this script again."
    exit 1
fi

if grep -Eq "^(TELEGRAM_BOT_TOKEN|OPENAI_API_KEY)=replace-me$" "$CONFIG_FILE"; then
    echo "Edit $CONFIG_FILE before starting the bot."
    echo "TELEGRAM_BOT_TOKEN and OPENAI_API_KEY are still set to replace-me."
    exit 1
fi

if grep -Eq "^ALLOWED_TELEGRAM_USER_IDS=123456789$" "$CONFIG_FILE"; then
    echo "Edit $CONFIG_FILE before starting the bot."
    echo "ALLOWED_TELEGRAM_USER_IDS still has the example value."
    exit 1
fi

mkdir -p data

if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install -qqq --upgrade pip
"$VENV_DIR/bin/python" -m pip install -qqq -r requirements.txt
"$VENV_DIR/bin/python" main.py
