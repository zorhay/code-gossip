"""Restore interrupted/failed updates and retain backups when recovery fails."""

from __future__ import annotations

from pathlib import Path
import shutil

import installer
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .constants import INSTALLATION_FILE, PRESERVED_DIRECTORIES
from .entities import Installation, UpdateProgress, UpdateResult
from .errors import UpdateError
from .installation import owned_hooks
from .soundbar import restart_and_verify, stop_panel
from .source import cleanup_interrupted_sources, cleanup_source
from .storage import (installed_version, load_progress, load_recovery_installation,
                      read_json, report_progress, write_json)


def recover_interrupted_update(paths: UpdatePaths, config: UpdateConfig = DEFAULT_CONFIG) -> UpdateResult | None:
    previous = load_progress(paths)
    try:
        if previous.needs_recovery:
            restore_and_verify(paths, previous, config)
            report_progress(paths, previous, "failed", "Interrupted update recovered. Previous version restored.")
        cleanup_update(paths, previous)
        cleanup_interrupted_sources(paths)
    except Exception as error:
        return report_failure(paths, previous, recovery_failure_message(error))
    return None


def recover_and_report(paths: UpdatePaths, progress: UpdateProgress, error: Exception,
                       config: UpdateConfig = DEFAULT_CONFIG) -> UpdateResult:
    message = f"Update failed: {error}"
    if progress.needs_recovery:
        report_progress(paths, progress, "recovering", "Restoring the previous installation…")
        try:
            restore_and_verify(paths, progress, config)
            message += " Previous version restored."
        except Exception as recovery_error:
            message += " " + recovery_failure_message(recovery_error)
    return report_failure(paths, progress, message)


def restore_and_verify(paths: UpdatePaths, progress: UpdateProgress, config: UpdateConfig) -> None:
    if progress.port is None:
        raise UpdateError("Recovery has no recorded Soundbar port.")
    restored = restore_installation(paths, config)
    restart_and_verify(paths, restored, progress.port, restored.version, config)
    progress.needs_recovery = False


def restore_installation(paths: UpdatePaths, config: UpdateConfig = DEFAULT_CONFIG) -> Installation:
    record = load_recovery_installation(paths)
    stop_panel(paths, config)
    restore_runtime(paths)
    for agent, path in record.integrations.items():
        restore_hooks(paths.recovery / "hooks", agent, path)
    write_json(paths.installation, read_json(paths.recovery / INSTALLATION_FILE))
    return record


def restore_runtime(paths: UpdatePaths) -> None:
    for child in paths.root.iterdir():
        if child.name not in PRESERVED_DIRECTORIES:
            remove_path(child)
    shutil.copytree(paths.recovery / "runtime", paths.root, symlinks=True, dirs_exist_ok=True)


def restore_hooks(backup: Path, agent: str, path: Path) -> None:
    original_file = backup / (agent + ".json")
    original = installer.read_document(original_file)
    current = installer.read_document(path)
    if installer.merge_hooks(current, agent, {}) == installer.merge_hooks(original, agent, {}):
        shutil.copy2(original_file, path)
    else:
        # Another tool may have edited its hooks during installation.
        restored = installer.merge_hooks(current, agent, owned_hooks(original, agent))
        installer.write_hooks(path, current, restored)
    hook_backup = path.with_name(path.name + ".code-gossip-backup")
    saved_backup = backup / (agent + ".backup")
    if saved_backup.exists():
        shutil.copy2(saved_backup, hook_backup)
    else:
        hook_backup.unlink(missing_ok=True)


def cleanup_update(paths: UpdatePaths, progress: UpdateProgress) -> None:
    cleanup_source(paths, progress.work)
    if not progress.needs_recovery and paths.recovery.exists():
        shutil.rmtree(paths.recovery)


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def recovery_failure_message(error: Exception) -> str:
    return f"Recovery needs attention: {error}. Backup retained in version_state/recovery."


def report_failure(paths: UpdatePaths, progress: UpdateProgress, message: str) -> UpdateResult:
    report_progress(paths, progress, "failed", message)
    return UpdateResult("failed", installed_version(paths.root), message)
