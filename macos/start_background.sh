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

cd "$DIR"

# Don't start a second copy if one is already running.
if pgrep -f "mac_main.py" >/dev/null 2>&1; then
    echo "Clickless macOS is already running."
    exit 0
fi

# Launch detached from this Terminal session. Clickless is an AppKit/Quartz
# app that needs the user's GUI (Aqua) session plus the Accessibility / Input
# Monitoring permissions granted to the launching terminal. Running it via
# `nohup` from the GUI session inherits those reliably; launching it from a
# plain `launchd` job does not, which made NSApplication exit immediately and
# the Shift hotkey stop working.
nohup "$POETRY_BIN" run python3 mac_main.py \
    > /tmp/clickless.out 2> /tmp/clickless.err < /dev/null &
disown

echo "Clickless macOS started in the background."
echo "Logs: /tmp/clickless.out  /tmp/clickless.err"
