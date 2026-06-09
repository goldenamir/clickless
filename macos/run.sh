#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ -x "$DIR/.venv-macos/bin/python" ]; then
    exec "$DIR/.venv-macos/bin/python" "$DIR/mac_main.py" "$@"
fi

exec python3 "$DIR/mac_main.py" "$@"
