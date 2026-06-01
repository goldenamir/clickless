#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
APPIMAGE="$HOME/Downloads/Mouseless_v1.0.0-preview.3_ubuntu-24.04_x86_64.AppImage"

"$DIR/stop.sh"
pkill -f "$APPIMAGE" 2>/dev/null && echo "Mouseless stopped." || echo "Mouseless was not running."
sleep 0.5
nohup "$APPIMAGE" > /dev/null 2>&1 &
echo "Mouseless started (PID $!)."
