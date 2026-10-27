"""JSON boundaries for installation records, checks, and update progress."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import json
import os
from pathlib import Path
import sys
import tempfile

from .config import UpdatePaths
from .constants import VERSION_FILE
from .entities import CheckResult, Installation, Release, UpdateProgress, UpdateStatus, Version


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root: Path) -> None:
    for directory, _, files in os.walk(root, topdown=False):
        for name in files:
            with (Path(directory) / name).open("rb") as stream:
                os.fsync(stream.fileno())
        sync_directory(directory)
    sync_directory(root.parent)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value) -> None:
    write_text(path, json.dumps(value, indent=2, default=serialize) + "\n")


def serialize(value):
    if isinstance(value, (Path, Version)):
        return str(value)
    if isinstance(value, Release):
        result = {"version": str(value.version), "tag": value.tag,
                  "id": value.id, "notes_url": value.notes_url}
        if value.asset_id is not None:
            result["asset_id"] = value.asset_id
        return result
    if is_dataclass(value):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def status_payload(status: UpdateStatus) -> dict:
    return {**serialize(status), "release": serialize(status.release) if status.release else None}


def installed_version(root: Path) -> str:
    try:
        return (root / VERSION_FILE).read_text().strip()
    except FileNotFoundError:
        return "development" if (root.resolve().parent / "install.sh").is_file() else "unknown"


def load_installation(paths: UpdatePaths) -> Installation | None:
    data = read_json(paths.installation)
    if not data:
        return None
    return Installation(version=data.get("version", "unknown"), mode=data.get("mode", "regular"),
                        root=Path(data.get("root", "")), python=data.get("python", ""),
                        integrations={agent: Path(path) for agent, path in data.get("integrations", {}).items()})


def record_installation(root: Path, paths, selected, dev=False, uninstall=False) -> None:
    """Remember exact destinations; Soundbar need not inherit CODEX_HOME."""
    locations = UpdatePaths(root)
    previous = load_installation(locations)
    integrations = dict(previous.integrations) if previous else {}
    for agent in selected:
        if uninstall:
            integrations.pop(agent, None)
        else:
            integrations[agent] = paths[agent]
    record = Installation(installed_version(root), "development" if dev else "regular",
                          root.resolve(), sys.executable, integrations)
    write_json(locations.installation, record)


def load_check(paths: UpdatePaths) -> CheckResult:
    data = read_json(paths.check)
    release = data.get("release")
    if release:
        release = Release(Version.parse(release["version"]), release["tag"], release["id"],
                          release["notes_url"], release.get("asset_id"))
    return CheckResult(release, data.get("checked_at"), data.get("attempted_at"), data.get("error", ""))


def load_progress(paths: UpdatePaths) -> UpdateProgress:
    data = read_json(paths.progress)
    values = {field.name: data[field.name] for field in fields(UpdateProgress) if field.name in data}
    if values.get("work"):
        values["work"] = Path(values["work"])
    return UpdateProgress(**values)


def report_progress(paths: UpdatePaths, progress: UpdateProgress, phase: str, message: str) -> None:
    progress.phase = phase
    progress.message = message
    write_json(paths.progress, progress)
    print(message, flush=True)
