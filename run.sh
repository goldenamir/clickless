#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export PATH="$HOME/.local/bin:$PATH"
exec poetry run python3 main.py "$@"
