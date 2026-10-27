"""Fixed product identity, file names, and release contents."""

REPOSITORY = "zorhay/code-gossip"
GITHUB_API = f"https://api.github.com/repos/{REPOSITORY}"
GITHUB_HEADERS = {
    "User-Agent": "Code-Gossip-Updater",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

VERSION_FILE = "VERSION"
VERSION_STATE_DIRECTORY = "version_state"
INSTALLATION_FILE = "installation.json"
CHECK_FILE = "check.json"
PROGRESS_FILE = "operation.json"
UPDATE_LOG_FILE = "update.log"
SOURCE_OWNER_FILE = "owner.json"
SOURCE_DIRECTORY_PREFIX = "code-gossip-update-"
ARCHIVE_FILE = "release.zip"
PACKAGE_ASSET = "code-gossip.zip"
ACTIVE_PHASES = {"checking", "preparing", "downloading", "installing", "restarting", "recovering"}

REQUIRED_SOURCE_FILES = (
    "install.sh", "code-gossip/installer.py", "code-gossip/VERSION",
    "code-gossip/updates/__init__.py", "code-gossip/soundbar/server.py",
    "code-gossip/hooks/codex.py", "code-gossip/hooks/cursor.py",
    "code-gossip/hooks/claude-hooks.json", "code-gossip/engine/play.sh",
    "code-gossip/configs/config.defaults.json", "code-gossip/data/sounds.json",
)
