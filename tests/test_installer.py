"""Exercise the public scripts against isolated homes, without audio or live hooks."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

import cursor
import installer


@pytest.fixture
def sandbox(tmp_path, repo_root, release_directory):
    home = tmp_path / "home with spaces"
    home.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    # A controlled PATH prevents detection of real apps' CLIs and macOS TTS.
    for name, executable in (("python3", sys.executable), ("dirname", shutil.which("dirname")), ("jq", shutil.which("jq"))):
        (binaries / name).symlink_to(executable)
    env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex"),
           "PATH": str(binaries), "PYTHONDONTWRITEBYTECODE": "1",
           "TEST_RELEASE_DIRECTORY": str(release_directory)}

    def run(script, *args, selection=None, success=True):
        path = Path(script)
        if not path.is_absolute():
            path = repo_root / path
        if path.name == "install.sh":
            args = (*args, "--no-panel")
        result = subprocess.run(["/bin/bash", str(path), *args], env=env,
                                input=selection or "", text=True, capture_output=True)
        if success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout
        return result

    return home, env, run


def document(home, agent):
    path = home / {"claude": ".claude/settings.json", "codex": ".codex/hooks.json", "cursor": ".cursor/hooks.json"}[agent]
    return json.loads(path.read_text()) if path.exists() else {}


def snapshot(home):
    return {str(path.relative_to(home)): path.read_bytes() for path in home.rglob("*") if path.is_file()}


def test_interactive_multi_selection_and_partial_uninstall(sandbox):
    home, _, run = sandbox
    for agent in installer.AGENTS:
        (home / f".{agent}").mkdir()
    result = run("install.sh", selection="2,3\n")
    assert "Detected agents: codex, cursor, claude" in result.stdout
    assert not document(home, "claude")
    assert installer.is_connected(document(home, "codex"), "codex")
    assert document(home, "cursor")["version"] == 1
    dest = home / ".code-gossip"
    # Partial uninstall must neither remove files nor stop the shared server.
    (dest / "state").mkdir(exist_ok=True)
    (dest / "state/.server.pid").write_text(str(os.getpid()))
    result = run(dest / "uninstall.sh", "--purge", selection="codex\n")
    assert "Keep shared Code Gossip files and processes for: cursor" in result.stdout
    assert (dest / "state/.server.pid").exists()
    (dest / "state/.server.pid").unlink()
    assert not installer.is_connected(document(home, "codex"), "codex")
    assert (dest / "engine/play.sh").exists()
    run(dest / "uninstall.sh", "--all")
    assert not (dest / "engine/play.sh").exists()
    assert set(p.name for p in (dest / "configs").iterdir()) == set(installer.USER_FILES)
    run("uninstall.sh", "--all", "--purge")
    assert not dest.exists()


def test_all_install_reinstall_and_uninstall_preserve_unrelated_hooks(sandbox):
    home, _, run = sandbox
    for agent in installer.AGENTS:
        (home / f".{agent}").mkdir()
    run("install.sh", "--all")
    paths = {agent: home / relative for agent, relative in {
        "codex": ".codex/hooks.json", "cursor": ".cursor/hooks.json", "claude": ".claude/settings.json"}.items()}
    for agent, path in paths.items():
        doc = json.loads(path.read_text())
        first = next(iter(doc["hooks"].values()))[0]
        if agent == "cursor":
            next(iter(doc["hooks"].values())).append({"command": "echo keep"})
        else:
            first["hooks"].append({"type": "command", "command": "echo keep"})
        doc["keep"] = True
        path.write_text(json.dumps(doc))
    dest = home / ".code-gossip"
    config = dest / "configs/config.json"
    config.write_text('{"voice_profile":"senior", "volume":17}')
    run("install.sh", "--agents", "all")
    assert json.loads(config.read_text())["volume"] == 17
    assert json.loads(config.read_text())["voice_profile"] == "senior"
    before = {agent: path.read_bytes() for agent, path in paths.items()}
    run("install.sh", "--all")
    assert before == {agent: path.read_bytes() for agent, path in paths.items()}
    run(dest / "uninstall.sh", "--all", "--purge")
    assert not dest.exists()
    for agent, path in paths.items():
        doc = json.loads(path.read_text())
        assert doc["keep"] is True
        assert "echo keep" in path.read_text()
        assert not installer.is_connected(doc, agent)


def test_dry_runs_do_not_write_or_stop_anything(sandbox):
    home, _, run = sandbox
    before = snapshot(home)
    run("install.sh", "--agents", "codex,cursor,claude", "--dry-run")
    assert snapshot(home) == before
    run("install.sh", "--agents", "codex")
    before = snapshot(home)
    run("uninstall.sh", "--all", "--purge", "--dry-run")
    assert snapshot(home) == before


def test_custom_codex_home(sandbox):
    home, env, run = sandbox
    custom = home / "custom codex"
    env["CODEX_HOME"] = str(custom)
    run("install.sh", "--agents", "codex")
    assert (custom / "hooks.json").exists()
    assert not (home / ".codex").exists()
    assert not (home / ".claude/settings.json").exists()
    run("uninstall.sh", "--all", "--purge")
    assert not installer.is_connected(json.loads((custom / "hooks.json").read_text()), "codex")


@pytest.mark.parametrize("invalid", ['broken', '[]', '{"hooks":[]}', '{"hooks":{"Stop":[{"hooks":null}]}}'])
def test_invalid_settings_abort_before_any_changes(sandbox, invalid):
    home, _, run = sandbox
    path = home / ".cursor/hooks.json"
    path.parent.mkdir()
    path.write_text(invalid)
    before = snapshot(home)
    run("install.sh", "--agents", "codex,cursor,claude", success=False)
    assert snapshot(home) == before
    run("uninstall.sh", "--all", success=False)
    assert snapshot(home) == before


def test_orphan_hooks_removed_without_shared_files(sandbox):
    home, _, run = sandbox
    path = home / ".claude/settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"command": "~/.code-gossip/engine/play.sh stop"}, {"command": "echo keep"}]}]}}))
    run("uninstall.sh", "--all")
    assert "code-gossip/engine/play.sh" not in path.read_text()
    assert "echo keep" in path.read_text()


def test_missing_selection_and_unknown_flags_fail_without_changes(sandbox):
    home, _, run = sandbox
    before = snapshot(home)
    result = run("install.sh", success=False)
    assert "No selection received" in result.stderr
    run("uninstall.sh", "--al", success=False)
    run("install.sh", "--agents", "typo", success=False)
    assert snapshot(home) == before


def test_dev_uninstall_never_deletes_checkout(sandbox, tmp_path, repo_root):
    home, _, run = sandbox
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(repo_root / "install.sh", checkout)
    shutil.copytree(repo_root / "code-gossip", checkout / "code-gossip",
                    ignore=shutil.ignore_patterns(*installer.USER_FILES, ".venv", "__pycache__",
                                                 "*.sock", "*.log", "session_context", "state"))
    (checkout / "uninstall.sh").symlink_to("code-gossip/uninstall.sh")
    run(checkout / "install.sh", "--dev", "--agents", "cursor,claude")
    dest = home / ".code-gossip"
    assert dest.is_symlink()
    run(checkout / "install.sh", "--agents", "codex", success=False)
    run(dest / "uninstall.sh", "--all", "--purge")
    assert not dest.is_symlink()
    assert (checkout / "code-gossip/engine/play.sh").exists()
    assert (checkout / "code-gossip/configs/config.json").exists()


def test_detection_and_all_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/bin/codex" if name == "codex" else None)
    paths = {agent: tmp_path / agent / "hooks.json" for agent in installer.AGENTS}
    # Hide actual host applications while retaining the test's directories.
    real_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda path: False if str(path).startswith("/Applications/") else real_is_dir(path))
    assert installer.detected_agents(tmp_path, paths) == ["codex"]
    assert installer.select_agents("all", ["codex"]) == ["codex"]
    paths["cursor"].parent.mkdir()
    (tmp_path / "Applications/Claude.app").mkdir(parents=True)
    assert installer.detected_agents(tmp_path, paths) == list(installer.AGENTS)
    assert installer.select_agents("2,4 codex", []) == ["codex", "claude"]


def test_shared_runtime_does_not_count_as_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    paths = {agent: tmp_path / f".{agent}" / "hooks.json" for agent in installer.AGENTS}
    (tmp_path / ".code-gossip").mkdir()
    real_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda path: False if str(path).startswith("/Applications/") else real_is_dir(path))
    assert installer.detected_agents(tmp_path, paths) == []
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text("{}")
    assert installer.detected_agents(tmp_path, paths) == ["claude"]


def test_unselected_invalid_settings_do_not_block_install(sandbox):
    home, _, run = sandbox
    path = home / ".cursor/hooks.json"
    path.parent.mkdir()
    path.write_text("broken")
    run("install.sh", "--agents", "codex")
    assert installer.is_connected(document(home, "codex"), "codex")
    assert path.read_text() == "broken"
    # Removal must still fail safely if another integration cannot be inspected.
    run("uninstall.sh", "--agents", "codex", success=False)
    assert (home / ".code-gossip/engine/play.sh").exists()


def test_uninstall_stops_running_panel(sandbox):
    home, env, run = sandbox
    run("install.sh", "--agents", "codex")
    dest = home / ".code-gossip"
    panel = subprocess.Popen([sys.executable, str(dest / "soundbar/server.py")],
                             env={**env, "PORT": "0"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not (dest / "state/.server.pid").exists() and panel.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert (dest / "state/.server.pid").read_text() == str(panel.pid)
        run("uninstall.sh", "--all", "--purge")
        assert panel.wait(timeout=5) != 0
        assert not dest.exists()
    finally:
        if panel.poll() is None:
            panel.terminate()
        panel.communicate(timeout=5)


@pytest.mark.parametrize("stale", ["invalid", "reused"])
def test_stale_pid_does_not_break_uninstall_or_kill_other_processes(sandbox, stale):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        dest = home / ".code-gossip"
        (dest / "state").mkdir(exist_ok=True)
        (dest / "state/.server.pid").write_text(str(unrelated.pid) if stale == "reused" else "not a pid")
        run("uninstall.sh", "--all", "--purge")
        assert unrelated.poll() is None
        assert not dest.exists()
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.parametrize("event,data,expected", [
    ("stop", {"status": "error"}, "error"),
    ("stop", {"status": "aborted"}, "interrupt"),
    ("stop", {"status": "completed"}, "stop"),
    ("afterShellExecution", {"command": "ls", "output": "files"}, "bash"),
    ("afterFileEdit", {"file_path": "test.py"}, "edit"),
])
def test_cursor_event_mapping(event, data, expected):
    sound, payload = cursor.normalize(event, {**data, "conversation_id": "abc"})
    assert sound == expected
    assert payload["soundbar_agent"] == "cursor"
    assert payload["session_id"] == "abc"


def test_cursor_hook_command_executes_without_output(tmp_path):
    soundbar = tmp_path / "path with spaces/code-gossip"
    (soundbar / "hooks").mkdir(parents=True)
    (soundbar / "engine").mkdir()
    shutil.copy2(Path(cursor.__file__), soundbar / "hooks/cursor.py")
    shutil.copy2(Path(cursor.__file__).parents[1] / "paths.py", soundbar / "paths.py")
    (soundbar / "engine/play.sh").write_text('printf "%s" "$1" > "$(dirname "$0")/event"\ncat > "$(dirname "$0")/payload"\necho hidden\n')
    command = cursor.hook_definitions(soundbar / "hooks/cursor.py")["stop"][0]["command"]
    result = subprocess.run(command, shell=True, input='{"status":"error"}', text=True, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert (soundbar / "engine/event").read_text() == "error"


@pytest.mark.parametrize("event,data,expected", [
    ("sessionStart", {}, "Cursor session"),
    ("sessionEnd", {}, "Cursor session closed"),
    ("stop", {"status": "completed"}, "Cursor finished this turn"),
    ("stop", {"status": "aborted"}, "interrupted the current Cursor turn"),
    ("postToolUseFailure", {"error_message": "access denied"}, "Cursor encountered a failure: access denied"),
    ("subagentStop", {}, "Sub-agent (agent) returned"),
    ("preCompact", {}, "Cursor is preparing to compact"),
    ("afterShellExecution", {"command": "ls", "output": "files"}, "Cursor ran a shell command: ls"),
])
def test_cursor_narration_uses_normalized_events(event, data, expected):
    from narrate import build_context
    _, payload = cursor.normalize(event, data)
    context = build_context(payload)
    assert expected in context
    assert "Codex" not in context
    assert "exit 0" not in context.lower()  # Cursor does not supply an exit code here.


def test_cached_hooks_are_silent_after_uninstall(sandbox):
    home, env, run = sandbox
    run("install.sh", "--agents", "codex,cursor,claude")
    commands = set()
    for agent in installer.AGENTS:
        for groups in document(home, agent)["hooks"].values():
            for group in groups:
                for handler in ([group] if agent == "cursor" else group["hooks"]):
                    commands.add(handler["command"])
    run("uninstall.sh", "--all", "--purge")
    for command in commands:
        result = subprocess.run(["/bin/sh", "-c", command], input="{}", env=env,
                                text=True, capture_output=True, timeout=5)
        assert result.returncode == 0, command
        assert result.stdout == result.stderr == "", command


@pytest.mark.parametrize("checkpoint", ["activate", "write_hooks", "record_installation", "commit"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("crash", [False, True])
def test_install_transaction_failure_boundaries(sandbox, release_package, tmp_path, checkpoint, existing, crash):
    """Exercise real entrypoints; os._exit bypasses every in-process finally block."""
    from updates.source import extract_archive
    home, env, run = sandbox
    hooks = home / ".codex/hooks.json"
    hooks.parent.mkdir()
    hooks.write_text('{"keep":true,"hooks":{"Stop":[{"hooks":[{"command":"echo unrelated"}]}]}}')
    if existing:
        run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    config = root / "configs/config.json"
    if existing:
        config.write_text(json.dumps({"python3_path": sys.executable, "effects_volume":23, "narrator_api_key":"fixture-secret"}))
        doc = json.loads(hooks.read_text())
        doc["hooks"]["Stop"][0]["hooks"].append({"command":"echo old code-gossip/hooks/codex.py"})
        hooks.write_text(json.dumps(doc))
    files = [hooks, home / ".claude/settings.json", config, root / "version_state/installation.json"]
    before = {path: path.read_bytes() if path.exists() else None for path in files}
    previous = os.readlink(root / "current") if existing else None
    package = extract_archive(release_package, tmp_path / "candidate")
    driver = tmp_path / "fault.py"
    driver.write_text('''import os, sys
sys.path.insert(0, sys.argv.pop(1))
import installer
from updates import recovery
name = os.environ['FAULT_POINT']
module = recovery if name in ('activate', 'commit') else installer
original = getattr(module, name)
fired = False
def fault(*args, **kwargs):
    global fired
    if fired:
        return original(*args, **kwargs)
    fired = True
    result = original(*args, **kwargs) if name != 'commit' else None
    if os.environ['FAULT_CRASH'] == '1':
        os._exit(23)
    raise OSError('injected transaction failure')
setattr(module, name, fault)
installer.main()
''')
    result = subprocess.run([sys.executable, "-B", str(driver), str(package / "code-gossip"),
                             "install", "--agents", "codex,claude", "--no-panel"],
                            env={**env, "FAULT_POINT":checkpoint, "FAULT_CRASH":str(int(crash))}, capture_output=True, text=True)
    assert result.returncode == (23 if crash else 1), result.stdout + result.stderr
    journal = root / "version_state/transaction.json"
    if crash:
        assert journal.exists()
        assert json.loads(run(root / "update.sh", "status", "--json").stdout)["phase"] == "interrupted"
        run(root / "update.sh", "update", success=existing)
    assert not journal.exists()
    assert {path: path.read_bytes() if path.exists() else None for path in files} == before
    assert (os.readlink(root / "current") if (root / "current").is_symlink() else None) == previous
    run(package / "install.sh", "--agents", "codex,claude")
    assert installer.is_connected(document(home, "claude"), "claude")


@pytest.mark.parametrize("purge", [False, True])
def test_uninstall_never_traverses_settings_symlink(tmp_path, purge):
    root, external = tmp_path / "runtime", tmp_path / "dotfiles"
    root.mkdir()
    external.mkdir()
    sentinel = external / "unrelated.txt"
    sentinel.write_text("preserve me")
    (root / "configs").symlink_to(external, target_is_directory=True)
    installer.remove_files(root, purge)
    assert sentinel.read_text() == "preserve me"


def test_reinstall_replaces_obsolete_code_and_preserves_state(sandbox):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    old = (root / "current").resolve()
    (old / "engine/obsolete.py").write_text("old code")
    (root / "state").mkdir()
    (root / "state/keep").write_text("runtime state")
    run("install.sh", "--agents", "codex")
    assert (root / "current").resolve() != old
    assert not (root / "engine/obsolete.py").exists()
    assert (old / "engine/obsolete.py").exists()
    assert (root / "state/keep").read_text() == "runtime state"


@pytest.mark.parametrize("pending", [False, True])
def test_switch_obeys_install_lock_and_pending_recovery(sandbox, pending):
    from contextlib import nullcontext
    from updates.process import lock
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    config = root / "configs/config.json"
    before = config.read_bytes()
    journal = root / "version_state/transaction.json"
    if pending:
        journal.write_text('{}')
    with nullcontext() if pending else lock(root):
        result = run(root / "switch.sh", "effects", "off", success=False)
        assert "Effects:" not in result.stdout
        assert config.read_bytes() == before
    journal.unlink(missing_ok=True)
    run(root / "switch.sh", "effects", "off")
    assert json.loads(config.read_text())["effects_on"] is False


def test_failed_atomic_settings_write_preserves_contents(tmp_path, monkeypatch):
    from updates import storage
    path = tmp_path / "config.json"
    path.write_text('{"secret":"keep"}')
    monkeypatch.setattr(storage.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        storage.write_json(path, {"secret":"changed"})
    assert path.read_text() == '{"secret":"keep"}'
    assert list(tmp_path.iterdir()) == [path]


def test_flat_install_requires_explicit_reinstall_preserving_settings(sandbox):
    home, _, run = sandbox
    root = home / ".code-gossip"
    (root / "engine").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "configs/config.json").write_text('{"effects_volume":17}')
    before = snapshot(home)
    assert "Flat installation" in run("install.sh", "--agents", "codex", success=False).stderr
    assert snapshot(home) == before
    run("uninstall.sh", "--all")
    run("install.sh", "--agents", "codex")
    assert json.loads((root / "configs/config.json").read_text())["effects_volume"] == 17


@pytest.mark.parametrize("location", ["configs", "state", "version_state", "version_state/releases", "current", "current-file"])
def test_install_rejects_unsafe_layout_before_mutation(sandbox, tmp_path, location):
    home, _, run = sandbox
    root = home / ".code-gossip"
    external = tmp_path / "unrelated"
    external.mkdir()
    (external / "keep").write_text("untouched")
    target = root / location.replace("-file", "")
    target.parent.mkdir(parents=True, exist_ok=True)
    if location == "current-file":
        target.write_text("not a pointer")
    else:
        target.symlink_to(external, target_is_directory=True)
    before = snapshot(home)
    run("install.sh", "--agents", "codex", success=False)
    assert snapshot(home) == before
    assert list(external.iterdir()) == [external / "keep"]


@pytest.mark.parametrize("change", ["external-hooks", "stage-failure", "missing-source"])
def test_preparation_preserves_active_install_and_concurrent_hook_edits(sandbox, release_package, tmp_path, change):
    from updates.source import extract_archive
    home, env, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    current = os.readlink(root / "current")
    config = (root / "configs/config.json").read_bytes()
    hooks = home / ".codex/hooks.json"
    before = hooks.read_bytes()
    package = extract_archive(release_package, tmp_path / "candidate")
    if change == "missing-source":
        (package / "code-gossip/update.sh").unlink()
    driver = tmp_path / "prepare.py"
    driver.write_text('''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv.pop(1))
import installer
original = installer.install_files
def prepare(*args):
    candidate = original(*args)
    if os.environ['CHANGE'] == 'stage-failure':
        raise OSError('preparation failed')
    hooks = Path.home() / '.codex/hooks.json'
    document = json.loads(hooks.read_text())
    document['external'] = 'keep concurrent edit'
    document['hooks']['Stop'].append({'hooks':[{'command':'echo unrelated'}]})
    hooks.write_text(json.dumps(document))
    return candidate
installer.install_files = prepare
installer.main()
''')
    result = subprocess.run([str(Path(env["PATH"]) / "python3"), "-B", str(driver), str(package / "code-gossip"),
                             "install", "--agents", "codex", "--no-panel"],
                            env={**env, "CHANGE":change}, capture_output=True, text=True)
    assert (result.returncode == 0) == (change == "external-hooks"), result.stderr
    if change == "external-hooks":
        assert json.loads(hooks.read_text())["external"] == "keep concurrent edit"
        assert "echo unrelated" in hooks.read_text()
    else:
        assert os.readlink(root / "current") == current
        assert hooks.read_bytes() == before
    assert (root / "configs/config.json").read_bytes() == config
    assert not (root / "version_state/transaction.json").exists()


def test_hook_write_refuses_concurrent_changes(tmp_path):
    path = tmp_path / "hooks.json"
    original = {"external": "before"}
    path.write_text('{"external":"after"}')
    with pytest.raises(ValueError, match="changed during installation"):
        installer.write_hooks(path, original, {**original, "hooks": {}})
    assert json.loads(path.read_text()) == {"external": "after"}


def test_dev_install_still_prepares_generals(tmp_path, repo_root, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/say")
    monkeypatch.setattr(installer.subprocess, "run", generated := Mock())
    source = repo_root / "code-gossip"
    assert installer.install_files(source, tmp_path, True) == source
    assert generated.call_args.args[0] == ["/bin/bash", str(source / "data/sounds/generals/generate.sh")]


def test_partial_release_copy_is_cleaned_before_retry(tmp_path, repo_root, monkeypatch):
    def fail_copy(source, candidate, **kwargs):
        candidate.mkdir()
        (candidate / "partial").write_text("incomplete copy")
        raise OSError("disk full")
    monkeypatch.setattr(installer.shutil, "copytree", fail_copy)
    with pytest.raises(OSError, match="disk full"):
        installer.install_files(repo_root / "code-gossip", tmp_path, False)
    assert list((tmp_path / "version_state/releases").iterdir()) == []


@pytest.mark.parametrize("action", ["install", "uninstall"])
def test_install_and_full_removal_refuse_running_kokoro_setup(sandbox, monkeypatch, action):
    import argparse
    from updates import soundbar
    from updates.errors import UpdateError
    home, _, run = sandbox
    run("install.sh", "--agents", "codex,claude")
    root = home / ".code-gossip"
    (root / "state").mkdir()
    (root / "state/.server.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setattr(installer, "owned_process", lambda *args: True)
    def installing(*args):
        raise UpdateError("Wait for Kokoro installation to finish")
    monkeypatch.setattr(soundbar, "ensure_panel_idle", installing)
    before = snapshot(home)
    args = argparse.Namespace(action=action, agents=["codex", "claude"], all=False,
                              dev=False, no_panel=True, dry_run=False, purge=True)
    with pytest.raises(UpdateError, match="Kokoro"):
        installer.run(args)
    assert snapshot(home) == before


@pytest.mark.parametrize("owned", [False, True])
def test_stop_process_recognizes_retained_generations_only(tmp_path, owned):
    root = tmp_path / "runtime"
    directory = root / ("version_state/releases/" + "a" * 32 + "/engine") if owned else tmp_path / "unrelated/engine"
    directory.mkdir(parents=True)
    script = directory / "kokoro_server.py"
    script.write_text("import time\nprint('ready', flush=True)\ntime.sleep(30)\n")
    child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        assert bool(installer.stop_process(child.pid, root / "engine/kokoro_server.py")) == owned
        if owned:
            assert child.wait(timeout=5) < 0
        else:
            assert child.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)


def custom_audio(root):
    """A registered user sample, absent from the published release package."""
    audio = root / "data/sounds/custom/local.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"user-owned audio")
    manifest = json.loads((root / "data/sounds.json").read_text())
    manifest["effects"]["custom"] = {"dir": "sounds/custom", "events": {"stop": {"file": "local.wav"}}}
    (root / "configs/sounds.json").write_text(json.dumps(manifest))
    return audio


def test_custom_audio_survives_repeated_reinstalls_and_release_cleanup(sandbox):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    first = (root / "current").resolve()
    local = custom_audio(root)
    manifest = json.loads((root / "configs/sounds.json").read_text())
    events = manifest["effects"]["custom"]["events"]
    events["edit"] = {"files": ["one.wav", "nested/two.wav"]}
    events["subagent_stop"] = {"sequence": [["three.wav", "four.wav"], ["five.wav"]]}
    events["permission"] = {"file": str(local)}  # Absolute stable installation path.
    manifest["voice"]["custom"] = {"dir": "sounds/custom", "events": {"stop": {"file": "voice.wav"}}}
    expected = {"local.wav": local.read_bytes()}
    for name in ["one.wav", "nested/two.wav", "three.wav", "four.wav", "five.wav", "voice.wav"]:
        path = local.parent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        expected[name] = path.read_bytes()
    external = home / "external.wav"
    external.write_bytes(b"external audio")
    events["session_start"] = {"file": str(external)}
    override = root / "configs/sounds.json"
    override.write_text(json.dumps(manifest))
    settings = override.read_bytes()
    shipped = root / "data/sounds/paper/book_open.mp3"
    release_bytes = shipped.read_bytes()
    shipped.write_bytes(b"old shipped sample")
    unused = local.parent / "unused.wav"
    unused.write_bytes(b"not registered")
    for _ in range(3):
        run("install.sh", "--agents", "codex")
        assert {name: (local.parent / name).read_bytes() for name in expected} == expected
        assert override.read_bytes() == settings
        assert shipped.read_bytes() == release_bytes, "New package owns shipped sample paths"
        assert not unused.exists(), "Unreferenced files must not accumulate across releases"
        assert external.read_bytes() == b"external audio"
    assert not first.exists(), "Custom samples must survive collection of their original generation"
    assert len(list((root / "version_state/releases").iterdir())) == 2


def test_still_referenced_retired_sample_is_preserved(sandbox):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    sample = custom_audio(root)
    # Simulate an old shipped sample still explicitly selected by the override.
    (root / "data/sounds.json").write_bytes((root / "configs/sounds.json").read_bytes())
    for _ in range(2):
        run("install.sh", "--agents", "codex")
        assert sample.read_bytes() == b"user-owned audio"


@pytest.mark.parametrize("problem", ["missing", "traversal", "file-link", "directory-link", "generation-path"])
def test_unsafe_custom_audio_stops_before_activation(sandbox, problem):
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    sample = custom_audio(root)
    external = home / "external"
    external.mkdir()
    (external / "local.wav").write_bytes(b"do not copy external content")
    manifest = json.loads((root / "configs/sounds.json").read_text())
    profile = manifest["effects"]["custom"]
    if problem == "missing":
        sample.unlink()
    elif problem == "traversal":
        profile["events"]["stop"]["file"] = "../../../installer.py"
    elif problem == "file-link":
        sample.unlink()
        sample.symlink_to(external / "local.wav")
    elif problem == "directory-link":
        sample.unlink()
        sample.parent.rmdir()
        sample.parent.symlink_to(external, target_is_directory=True)
    else:
        profile["events"]["stop"]["file"] = str(sample.resolve())
    (root / "configs/sounds.json").write_text(json.dumps(manifest))
    before, pointer = snapshot(home), os.readlink(root / "current")
    run("install.sh", "--agents", "codex", success=False)
    assert snapshot(home) == before
    assert os.readlink(root / "current") == pointer
    assert len(list((root / "version_state/releases").iterdir())) == 1
    assert not (root / "version_state/transaction.json").exists()


@pytest.mark.parametrize("same_contents", [False, True])
def test_custom_audio_collision_does_not_silently_replace_user_file(sandbox, release_package, tmp_path, same_contents):
    from updates.source import extract_archive
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    sample = custom_audio(root)
    package = extract_archive(release_package, tmp_path / "candidate")
    incoming = package / "code-gossip/data/sounds/custom/local.wav"
    incoming.parent.mkdir()
    incoming.write_bytes(sample.read_bytes() if same_contents else b"different incoming sample")
    before, pointer = snapshot(home), os.readlink(root / "current")
    result = run(package / "install.sh", "--agents", "codex", success=same_contents)
    assert sample.read_bytes() == b"user-owned audio"
    if not same_contents:
        assert "conflicts with the release package" in result.stderr
        assert snapshot(home) == before
        assert os.readlink(root / "current") == pointer


def test_audio_copy_failure_leaves_active_release_and_cleans_candidate(sandbox, release_package, tmp_path, monkeypatch):
    from updates.source import extract_archive
    home, _, run = sandbox
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    sample = custom_audio(root)
    package = extract_archive(release_package, tmp_path / "candidate")
    before, pointer = snapshot(home), os.readlink(root / "current")
    copy = installer.shutil.copy2
    def fail_sample(source, target, **kwargs):
        if Path(source) == sample.resolve():
            raise OSError("audio copy failed")
        return copy(source, target, **kwargs)
    monkeypatch.setattr(installer.shutil, "copy2", fail_sample)
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    with pytest.raises(OSError, match="audio copy failed"):
        installer.install_files(package / "code-gossip", root, False)
    assert snapshot(home) == before
    assert os.readlink(root / "current") == pointer
    assert len(list((root / "version_state/releases").iterdir())) == 1


def test_explicit_reinstall_can_restore_backed_up_audio_after_install(sandbox):
    home, _, run = sandbox
    root = home / ".code-gossip"
    (root / "configs").mkdir(parents=True)
    manifest = {"effects": {"custom": {"dir":"sounds/custom", "events":{"stop":{"file":"local.wav"}}}}, "voice": {}}
    (root / "configs/sounds.json").write_text(json.dumps(manifest))
    run("install.sh", "--agents", "codex")
    sample = root / "data/sounds/custom/local.wav"
    sample.parent.mkdir()
    sample.write_bytes(b"restored from user backup")
    run("install.sh", "--agents", "codex")
    assert sample.read_bytes() == b"restored from user backup"
