#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/HalflingWizard/telegram_gpt_chatbot.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

cd "$SCRIPT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "This script must run inside the telegram_gpt_chatbot git repo."
    exit 1
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch" == "HEAD" ]]; then
    echo "Cannot update from a detached HEAD. Check out a branch first."
    exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "$REPO_URL"
fi

origin_url="$(git remote get-url origin)"
if [[ "$origin_url" != "$REPO_URL" ]]; then
    echo "Origin points to $origin_url."
    echo "Expected $REPO_URL."
    echo "Update stopped so the wrong repo is not pulled."
    exit 1
fi

preserve_file() {
    local path="$1"
    if [[ -f "$path" ]]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$path")"
        cp -p "$path" "$BACKUP_DIR/$path"
    fi
}

restore_file() {
    local path="$1"
    if [[ -f "$BACKUP_DIR/$path" ]]; then
        mkdir -p "$(dirname "$path")"
        cp -p "$BACKUP_DIR/$path" "$path"
    fi
}

preserve_file ".env"
preserve_file ".env.local"
preserve_file "config.env"
preserve_file "data/telegram_gpt_bot.db"

echo "Fetching latest code from GitHub."
git fetch origin

echo "Pulling latest $current_branch with local changes autostashed."
git pull --ff-only --autostash origin "$current_branch"

restore_file ".env"
restore_file ".env.local"
restore_file "config.env"
restore_file "data/telegram_gpt_bot.db"

echo "Update complete. Local config and database files were preserved."
