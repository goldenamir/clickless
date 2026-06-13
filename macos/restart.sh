#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

"$DIR/stop.sh"
sleep 0.5
"$DIR/start_background.sh" "$@"
