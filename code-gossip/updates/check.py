"""Detect available releases, cache results, and schedule automatic checks."""

from dataclasses import replace
from pathlib import Path
import threading
import time

from . import github
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .entities import CheckResult, UpdateStatus, Version
from .errors import UpdateError
from .process import is_busy, lock
from .storage import installed_version, load_check, load_installation, load_progress, write_json


def check_for_updates(root: Path, force: bool = False, config: UpdateConfig = DEFAULT_CONFIG) -> CheckResult:
    """Manual checks bypass the cache; automatic failures retry at most hourly."""
    paths = UpdatePaths(root)
    with lock(root, "check", wait=True):
        cached = load_check(paths)
        now = time.time()
        if not force and check_is_recent(cached, now, config):
            return cached
        try:
            Version.parse(installed_version(root))
            result = CheckResult(github.latest_release(config), checked_at=now, attempted_at=now)
        except Exception as exc:
            write_json(paths.check, replace(cached, attempted_at=now, error=str(exc)))
            raise UpdateError(f"Could not check for updates: {exc}") from exc
        write_json(paths.check, result)
        return result


def check_is_recent(cached: CheckResult, now: float, config: UpdateConfig) -> bool:
    return (now - (cached.checked_at or 0) < config.check_interval
            or now - (cached.attempted_at or 0) < config.retry_interval)


def status(root: Path) -> UpdateStatus:
    paths = UpdatePaths(root)
    cached = load_check(paths)
    progress = load_progress(paths)
    installation = load_installation(paths)
    installed = installed_version(root)
    try:
        available = bool(cached.release and cached.release.version > Version.parse(installed))
    except UpdateError:
        available = False
    running = is_busy(root)
    interrupted = progress.interrupted(running)
    return UpdateStatus(
        installed=installed, release=cached.release, available=available, checked_at=cached.checked_at,
        development=bool(installation and installation.mode == "development"), running=running,
        phase="interrupted" if interrupted else progress.phase,
        message="Update was interrupted. Retry Update to recover and continue." if interrupted else progress.message,
        guidance=progress.guidance, operation_id=progress.started_at,
    )


def schedule_checks(root: Path, stop: threading.Event, config: UpdateConfig = DEFAULT_CONFIG) -> threading.Thread:
    thread = threading.Thread(target=watch_for_updates, args=(root, stop, config), name="release-check", daemon=True)
    thread.start()
    return thread


def watch_for_updates(root: Path, stop: threading.Event, config: UpdateConfig) -> None:
    while not stop.is_set():
        try:
            check_for_updates(root, config=config)
        except Exception:
            # Automatic discovery must never prevent Soundbar from starting.
            pass
        stop.wait(config.retry_interval)
