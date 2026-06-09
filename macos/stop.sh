#!/bin/bash
set -euo pipefail

if launchctl remove com.clickless.mac 2>/dev/null; then
    echo "Clickless macOS stopped."
else
    echo "Clickless macOS background job is not running."
fi

pkill -f "/clickless/macos/mac_main.py" 2>/dev/null || true
