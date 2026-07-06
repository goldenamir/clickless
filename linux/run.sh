#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export PATH="$HOME/.local/bin:$PATH"

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/clickless"
LOG_FILE="$LOG_DIR/linux.log"
mkdir -p "$LOG_DIR"

nohup setsid poetry run python3 main.py "$@" >>"$LOG_FILE" 2>&1 < /dev/null &
echo "Clickless started in the background."
echo "Log: $LOG_FILE"
echo "To stop it, run: ./stop.sh"
