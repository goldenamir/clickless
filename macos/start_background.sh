#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
SESSION_NAME="clickless-mac"
OUT_LOG="/tmp/clickless.out"
ERR_LOG="/tmp/clickless.err"

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
if pgrep -f "[m]ac_main.py" >/dev/null 2>&1; then
    echo "Clickless macOS is already running."
    exit 0
fi

# Clickless is an AppKit/Quartz app that needs a live user session. A plain
# detached nohup process can exit immediately after its parent shell closes, so
# prefer a lightweight terminal session host when one is available.
START_CMD="cd \"$DIR\" && exec \"$POETRY_BIN\" run python3 mac_main.py >> \"$OUT_LOG\" 2>> \"$ERR_LOG\""

if command -v tmux >/dev/null 2>&1; then
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    tmux new-session -d -s "$SESSION_NAME" "$START_CMD"
elif command -v screen >/dev/null 2>&1; then
    screen -S "$SESSION_NAME" -X quit >/dev/null 2>&1 || true
    screen -dmS "$SESSION_NAME" /bin/bash -lc "$START_CMD"
else
    nohup /bin/bash -lc "$START_CMD" > "$OUT_LOG" 2> "$ERR_LOG" < /dev/null &
    disown
fi

for _ in $(seq 1 20); do
    if pgrep -f "[m]ac_main.py" >/dev/null 2>&1; then
        echo "Clickless macOS started in the background."
        echo "Logs: $OUT_LOG  $ERR_LOG"
        exit 0
    fi
    sleep 0.1
done

echo "Clickless macOS failed to stay running." >&2
echo "Logs: $OUT_LOG  $ERR_LOG" >&2
exit 1
