"""Release discovery, source preparation, and real disposable update transactions."""
import io
import json
from copy import deepcopy
from pathlib import Path
import socket
import shutil
import time
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
from tests.test_installer import custom_audio, sandbox


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
def release_fixture(release_directory, release_package):
    def build(failure=None):
        if not failure:
            return release_directory
        with zipfile.ZipFile(release_package) as original, zipfile.ZipFile(release_directory / "release.zip", "w") as bundle:
            for member in original.infolist():
                data = original.read(member)
                if member.filename.endswith("/installer.py") and failure == "installer":
                    data = data.replace(b'            record_installation(root,', b'            raise OSError("fixture installer failure")\n            record_installation(root,')
                elif member.filename.endswith("/server.py") and failure == "health":
                    data = b'raise RuntimeError("fixture server failure")\n' + data
                bundle.writestr(member, data)
        return release_directory
    return build


@pytest.mark.parametrize("failure", [None, "installer", "health"])
def test_update_runs_fresh_installer_and_recovers(sandbox, release_fixture, failure):
    home, env, run = sandbox
    env["CODEX_HOME"] = str(home / "custom codex")
    run("install.sh", "--agents", "codex,claude")
    root = home / ".code-gossip"
    # Give the disposable installation an older version; keep the candidate intact.
    old_version = "0.8.0"
    (root / "VERSION").write_text(old_version + "\n")
    write_json(root / "version_state/installation.json",
               {**read_json(root / "version_state/installation.json"), "version": old_version})
    # A detected but unselected agent must not get integrated during an update.
    (home / ".cursor").mkdir()
    config = root / "configs/config.json"
    preferences = read_json(config)
    preferences.update(effects_volume=23, narrator_api_key="fixture-private-key")
    write_json(config, preferences)
    sample = custom_audio(root)
    manifest = (root / "configs/sounds.json").read_bytes()
    (root / "state").mkdir(exist_ok=True)
    (root / "state/keep").write_text("runtime state")
    (root / "current/__pycache__").mkdir(exist_ok=True)
    (root / "current/__pycache__/old.pyc").write_bytes(b"stale module")
    hooks_path = home / "custom codex/hooks.json"
    hooks = read_json(hooks_path)
    hooks["other_setting"] = "keep"
    hooks["hooks"].setdefault("Stop", []).append({"hooks": [{"type": "command", "command": "echo unrelated"}]})
    write_json(hooks_path, hooks)
    before = hooks_path.read_bytes()
    fixture = release_fixture(failure)
    target_version = read_json(fixture / "release.json")["tag_name"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Soundbar normally has no CODEX_HOME override; the updater must use its record.
    env.pop("CODEX_HOME")
    env.update(PORT=str(port), TEST_RELEASE_DIRECTORY=str(fixture))
    panel = subprocess.Popen([sys.executable, str(root / "soundbar/server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (root / "state/.server.pid").exists():
                break
            time.sleep(.02)
        assert (root / "state/.server.pid").exists()
        result = run(root / "update.sh", "check")
        assert f"Available: {target_version}" in result.stdout
        assert (root / "VERSION").read_text().strip() == old_version
        result = run(root / "update.sh", "update", success=not failure)
        operation = read_json(root / "version_state/operation.json")
        assert operation["phase"] == ("failed" if failure else "done"), (operation, result.stdout, result.stderr)
        expected = old_version if failure else target_version
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
        assert (root / "configs/sounds.json").read_bytes() == manifest
        assert sample.read_bytes() == b"user-owned audio"
        assert (root / "state/keep").read_text() == "runtime state"
        assert (root / "current/__pycache__/old.pyc").exists() == bool(failure)
        assert not Path(operation["work"]).exists()
        assert not (root / "version_state/transaction.json").exists()
        assert read_json(root / "version_state/installation.json")["version"] == expected
        assert operation["message"] in run(root / "update.sh", "status").stdout
        status = json.loads(run(root / "update.sh", "status", "--json").stdout)
        assert (status["installed"], status["message"], status["guidance"]) == (expected, operation["message"], "")
    finally:
        env["CODEX_HOME"] = str(home / "custom codex")
        run(root / "uninstall.sh", "--all", "--purge")


def staged_transaction(root, record):
    paths = UpdatePaths(root)
    candidate = paths.releases / ("a" * 32)
    shutil.copytree(paths.current.resolve(), candidate)
    target = str(candidate.relative_to(root))
    recovery.begin(paths, record.integrations, [paths.installation], candidate=target)
    recovery.activate(paths, target)
    return paths


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
    paths = staged_transaction(root, record)
    current = deepcopy(original)
    for groups in current["hooks"].values():
        groups.reverse()
    current["added_by_another_tool"] = True
    handlers = current["hooks"][event] if agent == "cursor" else current["hooks"][event][0]["hooks"]
    handlers.append({"type": "command", "command": "echo keep"})
    write_json(hook_path, current)
    assert installation.hook_signature(original, agent) == installation.hook_signature(current, agent)
    handlers[0]["command"] += " --changed-command"
    write_json(hook_path, current)
    assert installation.hook_signature(original, agent) != installation.hook_signature(current, agent)
    (root / "VERSION").write_text("0.9.0")
    recovery.recover(paths)
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
    (root / "VERSION").write_text("0.8.0\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(update, "check_for_updates", lambda *a, **kw: CheckResult(RELEASE))
    monkeypatch.setattr(github, "download_release", Mock(side_effect=UpdateError("Invalid archive")))
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
              if p.is_file() and "version_state" not in p.parts}
    with lock(root) as fd:
        assert update.run_update(root, fd) == 1
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
    paths = staged_transaction(root, record)
    (root / "VERSION").write_text("0.9.0")
    write_json(root / "version_state/operation.json", {"phase": "installing"})
    assert update_api.status(root)["phase"] == "interrupted"
    restart = Mock()
    monkeypatch.setattr(soundbar, "restart_and_verify", restart)
    def detect(*a, **kw):
        assert (root / "VERSION").read_text().strip() == record.version
        return CheckResult(Release(Version.parse(record.version), record.version, 9, RELEASE.notes_url))
    monkeypatch.setattr(update, "check_for_updates", detect)
    with lock(root) as fd:
        assert update.run_update(root, fd) == 0
    restart.assert_not_called()  # Recovery preserves a previously stopped panel.
    assert not (root / "version_state/transaction.json").exists()


@pytest.mark.parametrize("failure", ["restore_file", "activate", "commit"])
def test_recovery_failure_keeps_executable_and_retries(sandbox, monkeypatch, failure):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    monkeypatch.setattr(Path, "home", lambda: home)
    record = installation.prepare_installation(UpdatePaths(root))
    paths = staged_transaction(root, record)
    with monkeypatch.context() as fault:
        fault.setattr(recovery, failure, Mock(side_effect=OSError("disk full")))
        with lock(root) as fd:
            assert update.run_update(root, fd) == 1
    assert paths.transaction.exists()
    assert (root / "update.sh").is_file()
    assert (root / "VERSION").read_text().strip() == record.version
    assert "disk full" in read_json(paths.progress)["message"]
    run(root / "update.sh", "update")
    assert not paths.transaction.exists()


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
