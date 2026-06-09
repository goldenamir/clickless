#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/stop.sh"
sleep 0.5
"$DIR/run.sh" "$@"
