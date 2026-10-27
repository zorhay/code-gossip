"""Validate the installed integrations, snapshot them, and run the fresh installer."""

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import installer
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .entities import Installation
from .errors import UpdateError
from .storage import load_installation, read_json


def prepare_installation(paths: UpdatePaths) -> Installation:
    record = require_regular_installation(paths)
    validate_integrations(record)
    return replace(record, python=configured_python(paths, record))


def require_regular_installation(paths: UpdatePaths) -> Installation:
    root = paths.root
    record = load_installation(paths)
    if (record and record.mode == "development") or (Path.home() / ".code-gossip").is_symlink():
        raise UpdateError("Development installation: update your checkout, then run install.sh --dev with your existing agents.")
    if (not paths.current.is_symlink() or not record or record.root != root.resolve()
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
