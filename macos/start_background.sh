#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$DIR/.venv-macos/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Missing macOS virtual environment. Run ./install.sh first."
    exit 1
fi

launchctl remove com.clickless.mac 2>/dev/null || true
launchctl submit -l com.clickless.mac -- "$PYTHON" "$DIR/mac_main.py"
echo "Clickless macOS started in the background."
