"""Validate the installed integrations, snapshot them, and run the fresh installer."""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess

import installer
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .constants import PRESERVED_DIRECTORIES
from .entities import Installation, UpdatePlan, UpdateProgress
from .errors import UpdateError
from .storage import load_installation, read_json, report_progress, save_recovery_installation


def run_fresh_installer(plan: UpdatePlan, source: Path, progress: UpdateProgress) -> None:
    from .soundbar import stop_panel

    # Persist recovery intent before the first runtime mutation.
    progress.needs_recovery = True
    report_progress(plan.paths, progress, "installing", "Installing update…")
    stop_panel(plan.paths, plan.config)
    run_installer(source, plan.installation, plan.lock_fd, config=plan.config)


def prepare_installation(paths: UpdatePaths) -> Installation:
    record = require_regular_installation(paths)
    validate_integrations(record)
    return replace(record, python=configured_python(paths, record))


def require_regular_installation(paths: UpdatePaths) -> Installation:
    root = paths.root
    record = load_installation(paths)
    if (record and record.mode == "development") or (Path.home() / ".code-gossip").is_symlink():
        raise UpdateError("Development installation: update your checkout, then run install.sh --dev with your existing agents.")
    if (not record or record.root != root.resolve()
            or root.resolve() != (Path.home() / ".code-gossip").resolve()):
        raise UpdateError("Installation details are missing. Rerun install.sh with your existing agents and CODEX_HOME before updating.")
    return record


def validate_integrations(record: Installation) -> None:
    if not record.integrations:
        raise UpdateError("No integrations are recorded. Rerun install.sh with your existing agents.")
    for agent, path in record.integrations.items():
        if agent not in installer.AGENTS or not path.is_absolute():
            raise UpdateError("Invalid recorded integration. Rerun install.sh with your existing agents.")
        if not installer.is_connected(installer.read_document(path), agent):
            raise UpdateError(f"The recorded {agent} integration has changed. Rerun install.sh with the intended agents before updating.")
        if agent != "codex" and path != installer.targets(Path.home())[agent]:
            raise UpdateError(f"The recorded {agent} configuration path does not match this installation.")
        if agent == "codex" and path.name != "hooks.json":
            raise UpdateError("Invalid recorded Codex hook path.")


def configured_python(paths: UpdatePaths, record: Installation) -> str:
    config = read_json(paths.preferences)
    python = config.get("python3_path") or record.python
    if not python or not Path(python).is_absolute() or not os.access(python, os.X_OK):
        raise UpdateError("The configured Python executable is unavailable. Correct it before updating.")
    return python


def backup_installation(paths: UpdatePaths, record: Installation) -> None:
    root = paths.root
    backup = paths.recovery
    backup.mkdir(mode=0o700)
    shutil.copytree(root, backup / "runtime", symlinks=True,
                    ignore=lambda directory, names: PRESERVED_DIRECTORIES | {"__pycache__"} if Path(directory) == root else {"__pycache__"})
    hooks = backup / "hooks"
    hooks.mkdir()
    for agent, path in record.integrations.items():
        shutil.copy2(path, hooks / (agent + ".json"))
        previous_backup = path.with_name(path.name + ".code-gossip-backup")
        if previous_backup.exists():
            shutil.copy2(previous_backup, hooks / (agent + ".backup"))
    save_recovery_installation(paths, record)


def run_installer(source: Path, record: Installation, lock_fd: int, dry_run: bool = False,
                  config: UpdateConfig = DEFAULT_CONFIG) -> None:
    command = [record.python, "-B", str(source / "code-gossip/installer.py"), "install",
               "--agents", ",".join(record.integrations), "--no-panel",
               "--update-lock-fd", str(lock_fd)]
    if dry_run:
        command.append("--dry-run")
    subprocess.run(command, env=install_environment(record), pass_fds=(lock_fd,),
                   check=True, timeout=config.installer_timeout)


def install_environment(record: Installation) -> dict[str, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    codex = record.integrations.get("codex")
    if codex:
        env["CODEX_HOME"] = str(codex.parent)
    return env


def changed_hooks(paths: UpdatePaths, record: Installation) -> list[str]:
    backup = paths.recovery / "hooks"
    return [agent for agent, path in record.integrations.items()
            if hook_signature(read_json(backup / (agent + ".json")), agent) != hook_signature(read_json(path), agent)]


def hook_signature(document: dict, agent: str) -> list[str]:
    return sorted(json.dumps([event, [group] if agent == "cursor" else group], sort_keys=True)
                  for event, groups in owned_hooks(document, agent).items() for group in groups)


def owned_hooks(document: dict, agent: str) -> dict:
    owned = {}
    for event, groups in document.get("hooks", {}).items():
        for group in groups:
            handlers = [h for h in ([group] if agent == "cursor" else group.get("hooks", []))
                        if installer.owned(h, agent)]
            if handlers:
                owned.setdefault(event, []).extend(handlers if agent == "cursor" else [{**group, "hooks": handlers}])
    return owned
