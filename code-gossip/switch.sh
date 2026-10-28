#!/bin/bash
# Code Gossip — CLI control for Claude Code sound layers
# Usage: switch.sh <command> [value]

set -e
SOUNDBAR="$(cd "$(dirname "$0")" && pwd -P)"
SOUNDBAR="${SOUNDBAR%/version_state/releases/*}"
CFG="$SOUNDBAR/configs/config.json"
[ ! -f "$CFG" ] && CFG="$SOUNDBAR/configs/config.defaults.json"
[ ! -f "$CFG" ] && { echo "Code Gossip not installed. Run install.sh first."; exit 1; }

EFFECTS_PROFILES="default attention construction minimal paper sci-fi submarine wood-thrush silent"
VOICE_PROFILES="senior narrator generals empires"

# Read a config value
cfg_get() { jq -r ".$1 // \"$2\"" "$CFG" 2>/dev/null || echo "$2"; }

# All settings writers share the install/update lock and atomic JSON replacement.
cfg_set() {
  local python
  python=$(cfg_get python3_path "")
  [ -x "$python" ] || python=$(command -v python3)
  "$python" -B - "$SOUNDBAR" "$1" "$2" <<'PYTHON'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str((root / "current").resolve() if (root / "current").is_symlink() else root))
from updates.process import lock
from updates.storage import read_json, write_json
try:
    with lock(root, mutation=True):
        path = root / "configs/config.json"
        data = read_json(path if path.exists() else root / "configs/config.defaults.json")
        key, value = sys.argv[2:]
        data[key] = {"true": True, "false": False}.get(value, value)
        write_json(path, data)
except (OSError, ValueError, RuntimeError) as error:
    sys.exit(str(error))
PYTHON
}

CMD="$1"
VALUE="$2"

if [ -z "$CMD" ]; then
  EFX_ON=$(cfg_get effects_on true)
  EFX_PROF=$(cfg_get effects_profile default)
  VOX_ON=$(cfg_get voice_on false)
  VOX_PROF=$(cfg_get voice_profile senior)
  VOICE=$(cfg_get voice_main Tara)
  SUBVOICE=$(cfg_get voice_sub Aman)

  echo "=== Effects Layer ==="
  echo "  Enabled:  $EFX_ON"
  echo "  Profile:  $EFX_PROF"
  echo "  Profiles: $EFFECTS_PROFILES"
  echo ""
  echo "=== Voice Layer ==="
  echo "  Enabled:  $VOX_ON"
  echo "  Profile:  $VOX_PROF"
  echo "  Main:     $VOICE"
  echo "  Subagent: $SUBVOICE"
  echo "  Profiles: $VOICE_PROFILES"
  echo ""
  echo "Commands:"
  echo "  switch.sh effects [on|off]       Toggle effects layer"
  echo "  switch.sh effects-profile <name>  Switch effects profile"
  echo "  switch.sh voice [on|off]          Toggle voice layer"
  echo "  switch.sh voice-profile <name>    Switch voice profile"
  echo "  switch.sh main-voice <name>       Change main TTS voice"
  echo "  switch.sh sub-voice <name>        Change subagent TTS voice"
  exit 0
fi

case "$CMD" in
  effects)
    if [ -z "$VALUE" ]; then
      CURRENT=$(cfg_get effects_on true)
      [ "$CURRENT" = "true" ] && VALUE="false" || VALUE="true"
    else
      [ "$VALUE" = "on" ] && VALUE="true" || VALUE="false"
    fi
    cfg_set effects_on "$VALUE"
    echo "Effects: $VALUE"
    ;;

  effects-profile)
    if [ -z "$VALUE" ]; then
      echo "Current: $(cfg_get effects_profile default)"
      echo "Available: $EFFECTS_PROFILES"
      exit 0
    fi
    if ! echo "$EFFECTS_PROFILES" | grep -qw "$VALUE"; then
      echo "Unknown effects profile: $VALUE"
      echo "Available: $EFFECTS_PROFILES"
      exit 1
    fi
    cfg_set effects_profile "$VALUE"
    echo "Effects profile: $VALUE"
    ;;

  voice)
    if [ -z "$VALUE" ]; then
      CURRENT=$(cfg_get voice_on false)
      [ "$CURRENT" = "true" ] && VALUE="false" || VALUE="true"
    else
      [ "$VALUE" = "on" ] && VALUE="true" || VALUE="false"
    fi
    cfg_set voice_on "$VALUE"
    echo "Voice: $VALUE"
    if [ "$VALUE" = "true" ]; then
      V=$(cfg_get voice_main Tara)
      say -v "$V" -r 200 "Voice on" &
    fi
    ;;

  voice-profile)
    if [ -z "$VALUE" ]; then
      echo "Current: $(cfg_get voice_profile senior)"
      echo "Available: $VOICE_PROFILES"
      exit 0
    fi
    if ! echo "$VOICE_PROFILES" | grep -qw "$VALUE"; then
      echo "Unknown voice profile: $VALUE"
      echo "Available: $VOICE_PROFILES"
      exit 1
    fi
    cfg_set voice_profile "$VALUE"
    echo "Voice profile: $VALUE"
    ;;

  main-voice)
    if [ -z "$VALUE" ]; then
      echo "Current: $(cfg_get voice_main Tara)"
      exit 0
    fi
    cfg_set voice_main "$VALUE"
    say -v "$VALUE" -r 200 "Hello, I am $VALUE" &
    echo "Main voice: $VALUE"
    ;;

  sub-voice)
    if [ -z "$VALUE" ]; then
      echo "Current: $(cfg_get voice_sub Aman)"
      exit 0
    fi
    cfg_set voice_sub "$VALUE"
    say -v "$VALUE" -r 190 "Hello, I am $VALUE" &
    echo "Subagent voice: $VALUE"
    ;;

  *)
    # Backwards compat: bare profile name = switch effects profile
    if echo "$EFFECTS_PROFILES" | grep -qw "$CMD"; then
      cfg_set effects_profile "$CMD"
      echo "Effects profile: $CMD"
    else
      echo "Unknown command: $CMD"
      echo "Run without arguments for help."
      exit 1
    fi
    ;;
esac
