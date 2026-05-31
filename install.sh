#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Clickless installer ==="

# System dependencies
echo "[1/3] Installing system packages..."
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 xdotool python3-pip python3-venv

# Python venv with system GTK bindings
echo "[2/3] Setting up Python environment..."
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install pynput pyyaml

# Launcher script
echo "[3/3] Creating launcher..."
chmod +x run.sh

echo ""
echo "Done! Launch with:  ./run.sh"
echo "Hotkey:  Ctrl + Shift + G"
