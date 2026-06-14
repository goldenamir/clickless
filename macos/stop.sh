#!/bin/bash
set -euo pipefail

LABEL="com.clickless.mac"
UID_NUM="$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Clean up any legacy background jobs from older versions.
launchctl bootout "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
launchctl remove "$LABEL" 2>/dev/null || true
rm -f "$PLIST"

if pgrep -f "mac_main.py" >/dev/null 2>&1; then
    echo "Clickless macOS stopped."
else
    echo "Clickless macOS background job is not running."
fi

pkill -f "mac_main.py" 2>/dev/null || true

# Wait for the process(es) to actually exit so a restart can't race a
# still-running instance that still holds the keyboard event tap.
for _ in $(seq 1 20); do
    pgrep -f "mac_main.py" >/dev/null 2>&1 || break
    sleep 0.1
done

# Escalate to SIGKILL if anything is still alive.
if pgrep -f "mac_main.py" >/dev/null 2>&1; then
    pkill -9 -f "mac_main.py" 2>/dev/null || true
fi

# Wait for the process(es) to actually exit so a restart can't race a
# still-running instance that still holds the keyboard event tap.
for _ in $(seq 1 20); do
    pgrep -f "mac_main.py" >/dev/null 2>&1 || break
    sleep 0.1
done

# Escalate to SIGKILL if anything is still alive.
if pgrep -f "mac_main.py" >/dev/null 2>&1; then
    pkill -9 -f "mac_main.py" 2>/dev/null || true
fi
