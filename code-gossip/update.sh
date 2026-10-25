#!/bin/bash
# Check for releases or explicitly update the installed runtime.
set -euo pipefail
SND="$(cd "$(dirname "$0")" && pwd)"
CFG="$SND/configs/config.json"
[ -f "$CFG" ] || CFG="$SND/configs/config.defaults.json"
PYTHON3=""
if [ -f "$CFG" ] && command -v jq &>/dev/null; then
  PYTHON3=$(jq -r '.python3_path // ""' "$CFG")
fi
if [ -z "$PYTHON3" ] || [ ! -x "$PYTHON3" ]; then
  PYTHON3="$(command -v python3 2>/dev/null || echo /usr/bin/python3)"
fi
exec "$PYTHON3" -B "$SND/update.py" "$@"
