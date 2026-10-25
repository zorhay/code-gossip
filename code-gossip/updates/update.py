"""The update workflow: prepare → fresh source → install → verify or recover."""

from __future__ import annotations

from pathlib import Path
import time

from .check import check_for_updates
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .entities import UpdatePlan, UpdateProgress, UpdateResult, Version
from .errors import UpdateError
from .installation import backup_installation, changed_hooks, prepare_installation, run_fresh_installer
from .process import lock
from .recovery import cleanup_update, recover_and_report, recover_interrupted_update
from .soundbar import ensure_panel_idle, panel_port, restart_and_verify
from .source import prepare_source
from .storage import installed_version, report_progress


def run_update(root: Path, fd: int, config: UpdateConfig = DEFAULT_CONFIG) -> UpdateResult:
    paths = UpdatePaths(root)
    with lock(root, inherited=fd):
        recovery_failure = recover_interrupted_update(paths, config)
        if recovery_failure:
            return recovery_failure
        progress = UpdateProgress(started_at=time.time())
        try:
            plan = prepare_update(paths, progress, fd, config)
            if plan is None:
                return report_up_to_date(paths, progress)
            source = prepare_source(plan, progress)
            report_progress(paths, progress, "preparing", "Backing up the current installation…")
            backup_installation(paths, plan.installation)
            run_fresh_installer(plan, source, progress)
            verify_update(plan, progress)
            return report_success(plan, progress)
        except Exception as error:
            return recover_and_report(paths, progress, error, config)
        finally:
            cleanup_update(paths, progress)


def prepare_update(paths: UpdatePaths, progress: UpdateProgress, fd: int, config: UpdateConfig) -> UpdatePlan | None:
    report_progress(paths, progress, "checking", "Checking for the latest stable release…")
    release = check_for_updates(paths.root, force=True, config=config).release
    if release is None:
        raise UpdateError("No stable release was returned by the update check.")
    if release.version <= Version.parse(installed_version(paths.root)):
        return None
    installation = prepare_installation(paths)
    port = panel_port(paths, config)
    ensure_panel_idle(paths, port, config)
    progress.port = port
    progress.target = str(release.version)
    report_progress(paths, progress, "preparing", "Preparing update…")
    return UpdatePlan(paths, installation, release, port, fd, config)


def verify_update(plan: UpdatePlan, progress: UpdateProgress) -> None:
    report_progress(plan.paths, progress, "restarting", "Restarting and checking Soundbar…")
    restart_and_verify(plan.paths, plan.installation, plan.port, str(plan.release.version), plan.config)


def report_up_to_date(paths: UpdatePaths, progress: UpdateProgress) -> UpdateResult:
    message = "Code Gossip is up to date."
    report_progress(paths, progress, "done", message)
    return UpdateResult("up_to_date", installed_version(paths.root), message)


def report_success(plan: UpdatePlan, progress: UpdateProgress) -> UpdateResult:
    guidance = session_guidance(changed_hooks(plan.paths, plan.installation))
    progress.needs_recovery = False
    progress.guidance = guidance
    message = f"Updated to Code Gossip {plan.release.version}."
    report_progress(plan.paths, progress, "done", message)
    return UpdateResult("updated", str(plan.release.version), message, guidance)


def session_guidance(changed_agents: list[str]) -> str:
    if not changed_agents:
        return ""
    guidance = "Start a new session in " + ", ".join(changed_agents) + "."
    if "codex" in changed_agents:
        guidance += " Review changed commands in Codex CLI /hooks before starting a new chat."
    return guidance
