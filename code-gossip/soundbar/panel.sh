#!/bin/bash
# Soundbar — Control panel
# Opens an existing panel, or starts one. --background leaves it running.

SND="$(cd "$(dirname "$0")/.." && pwd -P)"
SND="${SND%/version_state/releases/*}"
LAUNCHER="$SND/soundbar/launcher.py"

# Resolve python3: config → which → fallback
CFG="$SND/configs/config.json"
[ ! -f "$CFG" ] && CFG="$SND/configs/config.defaults.json"
PYTHON3=""
if [ -f "$CFG" ] && command -v jq &>/dev/null; then
  PYTHON3=$(jq -r '.python3_path // ""' "$CFG" 2>/dev/null)
fi
if [ -z "$PYTHON3" ] || [ ! -x "$PYTHON3" ]; then
  PYTHON3="$(command -v python3 2>/dev/null || echo /usr/bin/python3)"
fi

exec "$PYTHON3" "$LAUNCHER" "$@"
