"""One durable journal for install, update and integration changes."""

import json
import os
from pathlib import Path
import re
import shutil

import installer
from .errors import UpdateError
from .storage import read_json, sync_directory, write_json, write_text


def validate_target(paths, target):
    if not re.fullmatch(r"version_state/releases/[0-9a-f]{32}", target):
        raise UpdateError("Invalid release generation.")
    if not (paths.root / target).is_dir() or (paths.root / target).is_symlink():
        raise UpdateError("Release generation is unavailable.")


def activate(paths, target):
    validate_target(paths, target)
    temporary = paths.root / ".current-next"
    temporary.unlink(missing_ok=True)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, paths.current)
        sync_directory(paths.root)
    finally:
        temporary.unlink(missing_ok=True)


def begin(paths, hooks, files, candidate=None, dev_link=None, port=None, runtime=True):
    if paths.transaction.exists():
        raise UpdateError("Recover the pending installation before starting another.")
    journal = {"root": str(paths.root.resolve()), "previous": os.readlink(paths.current) if paths.current.is_symlink() else None,
               "candidate": candidate, "runtime": runtime, "dev_link": str(dev_link) if dev_link else None, "port": port,
               "files": {str(path): contents(path) for path in files},
               "hooks": {agent: {"path": str(path), "text": contents(path),
                                  "backup": contents(path.with_name(path.name + ".code-gossip-backup"))}
                         for agent, path in hooks.items()}}
    write_json(paths.transaction, journal)
    return journal


def recover(paths):
    if not paths.transaction.exists():
        return
    journal = read_json(paths.transaction)
    if not isinstance(journal, dict) or journal.get("root") != str(paths.root.resolve()):
        raise UpdateError("Installation journal belongs to another runtime.")
    from .soundbar import stop_panel, restart_and_verify
    from .installation import owned_hooks
    from .storage import load_installation

    if journal["runtime"]:
        stop_panel(paths)
    if journal["previous"]:
        activate(paths, journal["previous"])
    for agent, saved in journal["hooks"].items():
        path = Path(saved["path"])
        original = json.loads(saved["text"]) if saved["text"] is not None else {}
        current = installer.read_document(path)
        if installer.merge_hooks(current, agent, {}) == installer.merge_hooks(original, agent, {}):
            restore_file(path, saved["text"])
        else:
            installer.write_hooks(path, current, installer.merge_hooks(current, agent, owned_hooks(original, agent)))
        restore_file(path.with_name(path.name + ".code-gossip-backup"), saved["backup"])
    for path, value in journal["files"].items():
        restore_file(Path(path), value)
    if journal["port"] is not None:
        record = load_installation(paths)
        if record:
            restart_and_verify(paths, record, journal["port"], record.version)
    commit(paths)
    # On first-install rollback keep the executable candidate until recovery succeeds.
    if journal["candidate"] and not journal["previous"]:
        paths.current.unlink(missing_ok=True)
    if journal["dev_link"]:
        link = Path(journal["dev_link"])
        if link.is_symlink() and link.resolve() == paths.root.resolve():
            link.unlink()


def commit(paths):
    paths.transaction.unlink(missing_ok=True)
    sync_directory(paths.version_state)


def collect_releases(paths, previous=None):
    keep = {paths.current.resolve(), (paths.root / previous).resolve() if previous else None}
    if paths.releases.is_dir() and not paths.releases.is_symlink():
        for child in paths.releases.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", child.name) and child.resolve() not in keep:
                remove_path(child)


def contents(path):
    return path.read_text() if path.exists() else None


def restore_file(path, value):
    if value is None:
        path.unlink(missing_ok=True)
    else:
        write_text(path, value)


def remove_path(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
