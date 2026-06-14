#!/bin/bash
set -euo pipefail

if launchctl remove com.clickless.mac 2>/dev/null; then
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
