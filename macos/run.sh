#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export PATH="$HOME/.local/bin:$PATH"

POETRY_BIN="${POETRY_BIN:-}"
if [ -z "$POETRY_BIN" ]; then
    POETRY_BIN="$(command -v poetry || true)"
fi
if [ -z "$POETRY_BIN" ] && [ -x "$HOME/.local/bin/poetry" ]; then
    POETRY_BIN="$HOME/.local/bin/poetry"
fi
if [ -z "$POETRY_BIN" ]; then
    echo "Poetry is required. Run ./install.sh first."
    exit 1
fi

exec "$POETRY_BIN" run python3 mac_main.py "$@"
