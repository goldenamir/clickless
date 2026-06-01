#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Clickless installer ==="

# System dependencies
echo "[1/3] Installing system packages..."
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 xdotool

# Install Poetry if not present
if ! command -v poetry &> /dev/null; then
    echo "[2/3] Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[2/3] Poetry already installed"
fi

# Install Python dependencies via Poetry
echo "[3/3] Installing Python dependencies..."
poetry install --no-root

# Launcher script
chmod +x run.sh

echo ""
echo "Done! Launch with:  ./run.sh"
