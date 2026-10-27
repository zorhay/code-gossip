"""Download a release and delegate every mutation to its transactional installer."""

from pathlib import Path
import time

import installer
from .check import check_for_updates
from .config import DEFAULT_CONFIG, UpdatePaths
from .entities import UpdateProgress, Version
from .installation import hook_signature, prepare_installation, run_installer
from .process import lock
from .recovery import recover
from .source import create_workspace, fetch_source, cleanup_source, cleanup_interrupted_sources
from .storage import installed_version, report_progress


def run_update(root: Path, fd: int, config=DEFAULT_CONFIG) -> int:
    paths = UpdatePaths(root)
    progress = UpdateProgress(started_at=time.time())
    with lock(root, inherited=fd):
        try:
            recover(paths)
            cleanup_interrupted_sources(paths)
            report_progress(paths, progress, "checking", "Checking for the latest stable release…")
            release = check_for_updates(root, force=True, config=config).release
            if release.version <= Version.parse(installed_version(root)):
                report_progress(paths, progress, "done", "Code Gossip is up to date.")
                return 0
            record = prepare_installation(paths)
            before = {agent: hook_signature(installer.read_document(path), agent) for agent, path in record.integrations.items()}
            progress.work = create_workspace(paths)
            report_progress(paths, progress, "downloading", f"Downloading Code Gossip {release.version}…")
            source = fetch_source(release, progress.work, config)
            run_installer(source, record, fd, dry_run=True, config=config)
            report_progress(paths, progress, "installing", "Installing and verifying update…")
            run_installer(source, record, fd, config=config)
            changed = [agent for agent, path in record.integrations.items()
                       if before[agent] != hook_signature(installer.read_document(path), agent)]
            progress.guidance = session_guidance(changed)
            report_progress(paths, progress, "done", f"Updated to Code Gossip {release.version}.")
            return 0
        except Exception as error:
            message = f"Update failed: {error}"
            try:
                recover(paths)
            except Exception as recovery_error:
                message += f" Recovery needs attention: {recovery_error}. Retry Update; previous release and journal retained."
            report_progress(paths, progress, "failed", message)
            return 1
        finally:
            cleanup_source(paths, progress.work)


def session_guidance(changed_agents: list[str]) -> str:
    if not changed_agents:
        return ""
    guidance = "Start a new session in " + ", ".join(changed_agents) + "."
    if "codex" in changed_agents:
        guidance += " Review changed commands in Codex CLI /hooks before starting a new chat."
    return guidance
