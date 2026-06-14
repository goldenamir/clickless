#!/bin/bash
set -euo pipefail

LABEL="com.clickless.mac"
SESSION_NAME="clickless-mac"
UID_NUM="$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Clean up any legacy background jobs from older versions.
launchctl bootout "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
launchctl remove "$LABEL" 2>/dev/null || true
rm -f "$PLIST"
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
screen -S "$SESSION_NAME" -X quit >/dev/null 2>&1 || true

if pgrep -f "[m]ac_main.py" >/dev/null 2>&1; then
    echo "Clickless macOS stopped."
else
    echo "Clickless macOS background job is not running."
fi

pkill -f "[m]ac_main.py" 2>/dev/null || true

# Wait for the process(es) to actually exit so a restart can't race a
# still-running instance that still holds the keyboard event tap.
for _ in $(seq 1 20); do
    pgrep -f "[m]ac_main.py" >/dev/null 2>&1 || break
    sleep 0.1
done

# Escalate to SIGKILL if anything is still alive.
if pgrep -f "[m]ac_main.py" >/dev/null 2>&1; then
    pkill -9 -f "[m]ac_main.py" 2>/dev/null || true
fi
