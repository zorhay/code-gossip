"""Cross-process locking and detached update-worker launch."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess

from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .errors import Busy, UpdateError
from .storage import load_progress, load_recovery_installation


def start_update(root: Path, config: UpdateConfig = DEFAULT_CONFIG) -> subprocess.Popen | None:
    """Detach before slow work so the server/terminal never owns the update."""
    from .installation import prepare_installation
    from .soundbar import ensure_panel_idle, panel_port

    paths = UpdatePaths(root)
    try:
        with lock(root) as fd:
            recovering = load_progress(paths).needs_recovery
            record = load_recovery_installation(paths) if recovering else prepare_installation(paths)
            ensure_panel_idle(paths, panel_port(paths, config), config)
            return launch_worker(paths, record.python, fd)
    except Busy:
        return None


def launch_worker(paths: UpdatePaths, python: str, fd: int) -> subprocess.Popen:
    with paths.log.open("a") as log:
        return subprocess.Popen(
            [python, "-B", str(paths.root / "update.py"), "_run", "--lock-fd", str(fd)],
            cwd=paths.root, start_new_session=True, pass_fds=(fd,),
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        )


@contextmanager
def lock(root: Path, name: str = "update", inherited: int | None = None, wait: bool = False):
    directory = UpdatePaths(root).version_state
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (name + ".lock")
    if inherited is not None:
        # Only the independent updater passes this descriptor to its installer.
        if not os.path.samestat(os.fstat(inherited), path.stat()):
            raise UpdateError("Invalid inherited update lock.")
        yield inherited
        return
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise Busy("An installation or update is already running. Wait for it to finish.") from None
        # Closing releases the lock, unless a detached worker/installer inherited
        # this same descriptor. Explicit LOCK_UN would also unlock its copy.
        yield stream.fileno()


def is_busy(root: Path) -> bool:
    try:
        with lock(root):
            return False
    except Busy:
        return True
