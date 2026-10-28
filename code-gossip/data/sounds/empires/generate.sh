#!/bin/bash
# Authoring only. Runtime plays the bundled MP3s without a speech engine.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$DIR/generate.py" "$@"
