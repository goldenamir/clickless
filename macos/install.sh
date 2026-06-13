#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Clickless macOS installer ==="

if ! command -v poetry &> /dev/null; then
    echo "[1/3] Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[1/3] Poetry already installed"
fi

echo "[2/3] Installing Python dependencies..."
poetry install --no-root

echo "[3/3] Preparing launcher..."
chmod +x run.sh start_background.sh stop.sh restart.sh

echo ""
echo "Done. Launch with: ./run.sh"
echo ""
echo "macOS will require Accessibility permission for the terminal or app"
echo "that runs Clickless:"
echo "System Settings -> Privacy & Security -> Accessibility"
