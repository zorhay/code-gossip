"""Shared package paths, resolved from this checkout or installed copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIGS = ROOT / "configs"
DATA = ROOT / "data"
ENGINE = ROOT / "engine"
STATE = ROOT / "state"
VERSION_STATE = ROOT / "version_state"
SOUNDBAR = ROOT / "soundbar"


def executable(name):
    """Find audio tools even when a hook or launcher has a restricted PATH."""
    import os
    import shutil
    found = shutil.which(name)
    if found:
        return found
    for directory in ("/usr/bin", "/opt/homebrew/bin", "/usr/local/bin"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
