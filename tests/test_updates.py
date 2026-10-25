"""Release discovery, source preparation, and real disposable update transactions."""
import io
import json
from copy import deepcopy
from pathlib import Path
import socket
import stat
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
import zipfile

import pytest
import installer
import updates as update_api
from updates import check, github, installation, process, recovery, soundbar, source, update
from updates.config import DEFAULT_CONFIG, UpdatePaths
from updates.entities import CheckResult, Release, Version
from updates.errors import Busy, UpdateError
from updates.process import is_busy, lock
from updates.storage import read_json, serialize, write_json
from tests.test_installer import sandbox


RELEASE = Release(Version.parse("0.9.0"), "0.9.0", 9,
                  "https://github.com/zorhay/code-gossip/releases/tag/0.9.0")


def test_detection_cache_manual_refresh_and_failure(tmp_path, monkeypatch):
    (tmp_path / "VERSION").write_text("0.8.0")
    discover = Mock(return_value=RELEASE)
    monkeypatch.setattr(github, "latest_release", discover)
    assert update_api.check_for_updates(tmp_path)["available"]
    assert update_api.check_for_updates(tmp_path)["available"]
    assert discover.call_count == 1
    update_api.check_for_updates(tmp_path, force=True)
    assert discover.call_count == 2
    discover.side_effect = OSError("offline")
    with pytest.raises(UpdateError, match="offline"):
        update_api.check_for_updates(tmp_path, force=True)
    assert update_api.status(tmp_path)["available"]
    assert update_api.status(tmp_path)["release"] == serialize(RELEASE)
    assert not (tmp_path / "version_state/installation.json").exists()
    cached = read_json(tmp_path / "version_state/check.json")
    cached["checked_at"] = 0
    write_json(tmp_path / "version_state/check.json", cached)
    update_api.check_for_updates(tmp_path)
    assert discover.call_count == 3, "Failures must not cause automatic request storms"
    cached["attempted_at"] = 0
    write_json(tmp_path / "version_state/check.json", cached)
    with pytest.raises(UpdateError):
        update_api.check_for_updates(tmp_path)
    assert discover.call_count == 4


def test_versions_and_release_validation(monkeypatch):
    assert Version.parse("v0.10.0") > Version.parse("0.9.99")
    for invalid in ("main", "0.9.0-rc1", "../0.9.0", "1.2", "01.2.3"):
        with pytest.raises(UpdateError):
            Version.parse(invalid)
    monkeypatch.setattr(github, "request", lambda url, timeout: io.BytesIO(json.dumps(
        {"tag_name": "0.9.0", "id": 9, "prerelease": True}).encode()))
    with pytest.raises(UpdateError, match="stable"):
        github.latest_release()


@pytest.mark.parametrize("name,mode", [("../../escape", 0), ("/absolute", 0),
                                        ("release/code-gossip/link", stat.S_IFLNK | 0o777)])
def test_unsafe_archives_are_rejected(tmp_path, name, mode):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo(name)
        info.external_attr = mode << 16
        bundle.writestr(info, "bad")
    with pytest.raises(UpdateError):
        source.extract_archive(archive, tmp_path / "source")
    assert not (tmp_path.parent / "escape").exists()


def test_update_lock_survives_parent_handoff(tmp_path):
    with lock(tmp_path) as fd:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"], pass_fds=(fd,))
    try:
        assert is_busy(tmp_path)
        with pytest.raises(Busy):
            with lock(tmp_path):
                pass
    finally:
        child.wait(timeout=5)
    assert not is_busy(tmp_path)


def test_metadata_tracks_selected_integrations_and_custom_home(sandbox):
    home, env, run = sandbox
    custom = home / "custom codex"
    env["CODEX_HOME"] = str(custom)
    run("install.sh", "--agents", "codex")
    run("install.sh", "--agents", "claude")
    root = home / ".code-gossip"
    metadata = read_json(root / "version_state/installation.json")
    assert metadata["integrations"] == {"codex": str(custom / "hooks.json"),
                                         "claude": str(home / ".claude/settings.json")}
    assert metadata["version"] == (root / "VERSION").read_text().strip()
    run(root / "uninstall.sh", "--agents", "claude")
    assert set(read_json(root / "version_state/installation.json")["integrations"]) == {"codex"}


@pytest.fixture
def release_fixture(tmp_path, repo_root):
    fixture = tmp_path / "release"
    fixture.mkdir()
    write_json(fixture / "release.json", {"tag_name": "0.9.0", "id": 9, "draft": False, "prerelease": False})

    def build(failure=None):
        with zipfile.ZipFile(fixture / "release.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(repo_root / "install.sh", "release/install.sh")
            for path in (repo_root / "code-gossip").rglob("*"):
                relative = path.relative_to(repo_root)
                if not path.is_file() or any(part in ("state", "version_state", "__pycache__") for part in relative.parts):
                    continue
                if path.name in (*installer.USER_FILES, "sounds.json") and path.parent.name == "configs":
                    continue
                data = path.read_bytes()
                if path.name == "VERSION":
                    data = b"0.9.0\n"
                elif path.name == "installer.py" and failure == "installer":
                    data = data.replace(b'if not args.no_panel:', b'raise OSError("fixture installer failure")\n        if not args.no_panel:')
                elif path.name == "server.py" and failure == "health":
                    data = b'raise RuntimeError("fixture server failure")\n' + data
                bundle.writestr("release/" + str(relative), data)
        return fixture
    return build


@pytest.mark.parametrize("failure", [None, "installer", "health"])
def test_update_runs_fresh_installer_and_recovers(sandbox, release_fixture, failure):
    home, env, run = sandbox
    env["CODEX_HOME"] = str(home / "custom codex")
    run("install.sh", "--agents", "codex,claude")
    root = home / ".code-gossip"
    # A detected but unselected agent must not get integrated during an update.
    (home / ".cursor").mkdir()
    config = root / "configs/config.json"
    preferences = read_json(config)
    preferences.update(effects_volume=23, narrator_api_key="fixture-private-key")
    write_json(config, preferences)
    (root / "configs/sounds.json").write_text('{"custom":true}')
    (root / "state").mkdir(exist_ok=True)
    (root / "state/keep").write_text("runtime state")
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__/old.pyc").write_bytes(b"stale module")
    hooks_path = home / "custom codex/hooks.json"
    hooks = read_json(hooks_path)
    hooks["other_setting"] = "keep"
    hooks["hooks"].setdefault("Stop", []).append({"hooks": [{"type": "command", "command": "echo unrelated"}]})
    write_json(hooks_path, hooks)
    before = hooks_path.read_bytes()
    old_version = (root / "VERSION").read_text().strip()
    fixture = release_fixture(failure)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Soundbar normally has no CODEX_HOME override; the updater must use its record.
    env.pop("CODEX_HOME")
    env.update(PORT=str(port), TEST_RELEASE_DIRECTORY=str(fixture))
    try:
        result = run(root / "update.sh", "check")
        assert "Available: 0.9.0" in result.stdout
        assert (root / "VERSION").read_text().strip() == old_version
        result = run(root / "update.sh", "update", success=not failure)
        operation = read_json(root / "version_state/operation.json")
        assert operation["phase"] == ("failed" if failure else "done"), (operation, result.stdout, result.stderr)
        expected = old_version if failure else "0.9.0"
        assert (root / "VERSION").read_text().strip() == expected
        assert soundbar.panel_request(port, "/api/health")["version"] == expected
        assert read_json(config)["effects_volume"] == 23
        assert read_json(config)["narrator_api_key"] == "fixture-private-key"
        if failure:
            assert hooks_path.read_bytes() == before
        else:
            current = read_json(hooks_path)
            assert installer.merge_hooks(current, "codex", {}) == installer.merge_hooks(hooks, "codex", {})
            def commands(document):
                return sorted((event, handler["command"]) for event, groups in document["hooks"].items()
                              for group in groups for handler in group["hooks"] if installer.owned(handler, "codex"))
            assert commands(current) == commands(hooks)
        assert operation.get("guidance", "") == "", "Reordering unchanged hooks must not require approval"
        assert not (home / ".cursor/hooks.json").exists()
        assert not (home / ".codex/hooks.json").exists()
        assert (root / "configs/sounds.json").read_text() == '{"custom":true}'
        assert (root / "state/keep").read_text() == "runtime state"
        assert not (root / "__pycache__/old.pyc").exists()
        assert not Path(operation["work"]).exists()
        assert not (root / "version_state/recovery").exists()
        assert read_json(root / "version_state/installation.json")["version"] == expected
        assert operation["message"] in run(root / "update.sh", "status").stdout
        status = json.loads(run(root / "update.sh", "status", "--json").stdout)
        assert (status["installed"], status["message"], status["guidance"]) == (expected, operation["message"], "")
        if failure:
            assert "Previous version restored" in operation["message"]
    finally:
        env["CODEX_HOME"] = str(home / "custom codex")
        run(root / "uninstall.sh", "--all", "--purge")


@pytest.mark.parametrize("agent", installer.AGENTS)
def test_recovery_preserves_external_hook_changes(sandbox, monkeypatch, agent):
    home, env, run = sandbox
    run("install.sh", "--agents", agent)
    root = home / ".code-gossip"
    monkeypatch.setattr(Path, "home", lambda: home)
    record = installation.prepare_installation(UpdatePaths(root))
    hook_path = record.integrations[agent]
    original = read_json(hook_path)
    event = next(iter(original["hooks"]))
    group = deepcopy(original["hooks"][event][0])
    group["timeout"] = 42  # Group/handler metadata must survive recovery too.
    original["hooks"][event].append(group)
    write_json(hook_path, original)
    installation.backup_installation(UpdatePaths(root), record)
    current = deepcopy(original)
    for groups in current["hooks"].values():
        groups.reverse()
    current["added_by_another_tool"] = True
    handlers = current["hooks"][event] if agent == "cursor" else current["hooks"][event][0]["hooks"]
    handlers.append({"type": "command", "command": "echo keep"})
    write_json(hook_path, current)
    assert installation.changed_hooks(UpdatePaths(root), record) == []
    handlers[0]["command"] += " --changed-command"
    write_json(hook_path, current)
    assert installation.changed_hooks(UpdatePaths(root), record) == [agent]
    (root / "VERSION").write_text("0.9.0")
    recovery.restore_installation(UpdatePaths(root))
    assert read_json(hook_path) == installer.merge_hooks(current, agent, original["hooks"])
    assert (root / "VERSION").read_text().strip() == record.version


def test_development_and_missing_metadata_do_not_update(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".code-gossip"
    root.mkdir()
    with pytest.raises(UpdateError, match="details are missing"):
        process.start_update(root)
    write_json(root / "version_state/installation.json", {"mode": "development"})
    with pytest.raises(UpdateError, match="Development installation"):
        process.start_update(root)


def test_cleanup_only_removes_owned_temporary_source(tmp_path):
    unowned = tmp_path / "code-gossip-update-not-ours"
    unowned.mkdir()
    source.cleanup_source(UpdatePaths(tmp_path), unowned)
    assert unowned.exists()


def test_failed_preparation_keeps_runtime_untouched(sandbox, monkeypatch):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(update, "ensure_panel_idle", lambda *args: None)
    monkeypatch.setattr(update, "check_for_updates", lambda *a, **kw: CheckResult(RELEASE))
    monkeypatch.setattr(github, "resolve_release", Mock(side_effect=UpdateError("Invalid archive")))
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
              if p.is_file() and "version_state" not in p.parts}
    with lock(root) as fd:
        assert update.run_update(root, fd).exit_code == 1
    after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
             if p.is_file() and "version_state" not in p.parts}
    assert before == after
    operation = read_json(root / "version_state/operation.json")
    assert "Invalid archive" in operation["message"]
    assert not Path(operation["work"]).exists()


def test_interrupted_update_restores_before_next_detection(sandbox, monkeypatch):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    monkeypatch.setattr(Path, "home", lambda: home)
    record = installation.prepare_installation(UpdatePaths(root))
    installation.backup_installation(UpdatePaths(root), record)
    (root / "VERSION").write_text("0.9.0")
    write_json(root / "version_state/operation.json", {"phase": "installing", "needs_recovery": True, "port": 8111})
    assert update_api.status(root)["phase"] == "interrupted"
    restart = Mock()
    monkeypatch.setattr(recovery, "restart_and_verify", restart)
    def detect(*a, **kw):
        assert (root / "VERSION").read_text().strip() == record.version
        return CheckResult(Release(Version.parse(record.version), record.version, 9, RELEASE.notes_url))
    monkeypatch.setattr(update, "check_for_updates", detect)
    with lock(root) as fd:
        assert update.run_update(root, fd).exit_code == 0
    restart.assert_called_once_with(UpdatePaths(root), record, 8111, record.version, DEFAULT_CONFIG)
    assert not (root / "version_state/recovery").exists()


def test_recovery_failure_retains_backup_and_error(sandbox, monkeypatch):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    backup = root / "version_state/recovery"
    backup.mkdir()
    (backup / "keep").write_text("backup")
    write_json(root / "version_state/operation.json", {"phase": "recovering", "needs_recovery": True, "port": 8111})
    monkeypatch.setattr(recovery, "restore_installation", Mock(side_effect=OSError("disk full")))
    with lock(root) as fd:
        assert update.run_update(root, fd).exit_code == 1
    assert (backup / "keep").read_text() == "backup"
    status = update_api.status(root)
    assert status["phase"] == "failed"
    assert "disk full" in status["message"]


def test_scheduler_checks_without_installing(monkeypatch, tmp_path):
    import threading
    stop = threading.Event()
    def detect(root, **kwargs):
        assert root == tmp_path
        stop.set()
    monkeypatch.setattr(check, "check_for_updates", detect)
    monkeypatch.setattr(process, "start_update", Mock(side_effect=AssertionError("Must not install")))
    check.schedule_checks(tmp_path, stop).join(timeout=2)
    assert stop.is_set()


def test_foreign_service_rejected_before_installation(monkeypatch, tmp_path):
    monkeypatch.setattr(soundbar, "panel_request", Mock(side_effect=HTTPError("http://localhost", 404, "Not found", {}, None)))
    with pytest.raises(UpdateError, match="another application"):
        soundbar.ensure_panel_idle(UpdatePaths(tmp_path), 8111)
    monkeypatch.setattr(soundbar, "panel_request", Mock(side_effect=URLError(TimeoutError())))
    with pytest.raises(UpdateError, match="Could not verify"):
        soundbar.ensure_panel_idle(UpdatePaths(tmp_path), 8111)
