#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
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

launchctl remove com.clickless.mac 2>/dev/null || true
launchctl submit -l com.clickless.mac -- /bin/bash -lc "cd '$DIR' && exec '$POETRY_BIN' run python3 mac_main.py"
echo "Clickless macOS started in the background."
