"""Update policy and paths, resolved from the selected runtime."""

from dataclasses import dataclass
from pathlib import Path

from . import constants


@dataclass(frozen=True)
class UpdateConfig:
    check_interval: int = 24 * 60 * 60
    retry_interval: int = 60 * 60
    request_timeout: int = 10
    response_limit: int = 1024 * 1024
    download_timeout: int = 30
    download_deadline: int = 180
    download_limit: int = 256 * 1024 * 1024
    download_chunk_size: int = 1024 * 1024
    extracted_limit: int = 512 * 1024 * 1024
    archive_member_limit: int = 20000
    installer_timeout: int = 300
    panel_default_port: int = 8111
    panel_request_timeout: int = 1
    panel_stop_timeout: int = 10
    panel_start_timeout: int = 15
    panel_terminate_timeout: int = 5
    panel_stop_poll_interval: float = 0.1
    panel_start_poll_interval: float = 0.2


DEFAULT_CONFIG = UpdateConfig()


@dataclass
class UpdatePaths:
    root: Path

    def __post_init__(self) -> None:
        self.version_state = self.root / constants.VERSION_STATE_DIRECTORY
        self.installation = self.version_state / constants.INSTALLATION_FILE
        self.check = self.version_state / constants.CHECK_FILE
        self.progress = self.version_state / constants.PROGRESS_FILE
        self.log = self.version_state / constants.UPDATE_LOG_FILE
        self.transaction = self.version_state / "transaction.json"
        self.releases = self.version_state / "releases"
        self.current = self.root / "current"
        self.panel_state = self.root / "state/panel.json"
        self.panel_pid = self.root / "state/.server.pid"
        self.panel_log = self.root / "state/panel.log"
        self.preferences = self.root / "configs/config.json"
