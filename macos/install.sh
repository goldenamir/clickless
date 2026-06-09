#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Clickless macOS installer ==="

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/3] Creating local virtual environment..."
"$PYTHON_BIN" -m venv .venv-macos

echo "[2/3] Installing Python dependencies..."
. .venv-macos/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[3/3] Preparing launcher..."
chmod +x run.sh start_background.sh stop.sh

echo ""
echo "Done. Launch with: ./run.sh"
echo ""
echo "macOS will require Accessibility permission for the terminal or app"
echo "that runs Clickless:"
echo "System Settings -> Privacy & Security -> Accessibility"
