"""Codex transport and recursion regression tests: no network or real audio."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import patch

import pytest
import narrate
from soundbar.catalog import NARRATOR_PROVIDERS
from tests.test_codex import codex


def fake_cli(tmp_path, monkeypatch, source):
    binary = tmp_path / "codex"
    binary.write_text(f"#!{sys.executable}\n" + source)
    binary.chmod(0o755)
    monkeypatch.setattr(narrate, "executable", lambda name: str(binary))
    return binary


def test_transport_isolated_prompt_and_final_stdout(tmp_path, monkeypatch):
    record = tmp_path / "request.json"
    monkeypatch.setenv("REQUEST_RECORD", str(record))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "existing-auth-home"))
    fake_cli(tmp_path, monkeypatch, '''import os,sys,json
from pathlib import Path
args = sys.argv[1:]
instruction = next(a.split("=",1)[1] for a in args if a.startswith("model_instructions_file="))
Path(os.environ["REQUEST_RECORD"]).write_text(json.dumps({
    "args": args, "prompt": sys.stdin.read(), "cwd": os.getcwd(),
    "guard": os.environ.get("CODE_GOSSIP_NARRATOR"),
    "auth_home": os.environ.get("CODEX_HOME"),
    "instructions": Path(json.loads(instruction)).read_text()}))
print("Private CLI diagnostics", file=sys.stderr)
print("  Updated the parser.  ")
''')
    assert narrate._dispatch("codex_cli", "chosen-model", "", "Speak naturally", "Edited parser.py") == "Updated the parser."
    request = json.loads(record.read_text())
    args = request["args"]
    assert args[0] == "exec" and args[-1] == "-"
    assert args[args.index("--model") + 1] == "chosen-model"
    for option in ("--ephemeral", "--ignore-user-config", "--skip-git-repo-check"):
        assert option in args
    for feature in ("hooks", "shell_tool", "plugins", "apps", "multi_agent"):
        assert args[args.index(feature) - 1] == "--disable"
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "project_doc_max_bytes=0" in args
    assert request["prompt"] == "Edited parser.py"
    assert "Speak naturally" in request["instructions"]
    assert request["guard"] == "1"
    assert request["auth_home"] == str(tmp_path / "existing-auth-home")
    assert not Path(request["cwd"]).exists(), "Temporary context must be cleaned up"


def test_default_model_and_catalog_agree(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, 'import sys\nassert "--model" not in sys.argv\nprint("Ready.")\n')
    assert narrate.PROVIDERS["codex_cli"] == NARRATOR_PROVIDERS["codex_cli"]
    assert narrate.call_provider("codex_cli", "", "", "Edited app.ts", "pair_programmer") == "Ready."


@pytest.mark.parametrize("available", [False, True])
def test_check_only_detects_executable(monkeypatch, available):
    monkeypatch.setattr(narrate, "executable", lambda name: "/bin/codex" if available else None)
    with patch.object(narrate.subprocess, "Popen") as process:
        assert narrate.check_provider("codex_cli", "", "")["ok"] is available
        process.assert_not_called()


def test_cli_discovery_with_restricted_hook_path(tmp_path, monkeypatch):
    import paths
    import shutil
    binary = tmp_path / ".local/bin/codex"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Keep the test independent of machine-wide CLI installations.
    real_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: path == binary and real_is_file(path))
    assert paths.executable("codex") == str(binary)


def test_missing_binary_and_failure_do_not_expose_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(narrate, "executable", lambda name: None)
    with pytest.raises(RuntimeError, match="not found"):
        narrate._call_codex_cli("", "System", "Event")
    fake_cli(tmp_path, monkeypatch, 'import sys\nprint("secret diagnostic", file=sys.stderr)\nprint("Do not speak partial output")\nsys.exit(1)\n')
    with pytest.raises(RuntimeError, match="Codex CLI failed") as error:
        narrate._call_codex_cli("", "System", "Event")
    assert "secret" not in str(error.value)


def test_timeout_kills_child_processes(tmp_path, monkeypatch):
    marker = tmp_path / "orphan.txt"
    ready = tmp_path / "child-started"
    start = tmp_path / "start-timer"
    child = f'''import time
from pathlib import Path
Path({str(ready)!r}).touch()
while not Path({str(start)!r}).exists():
    time.sleep(0.01)
time.sleep(1)
Path({str(marker)!r}).touch()
'''
    source = f'''import subprocess,sys,time
subprocess.Popen([sys.executable, "-c", {child!r}])
time.sleep(30)
'''
    fake_cli(tmp_path, monkeypatch, source)
    real_popen = subprocess.Popen

    def started_cli(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        try:
            # Test group cleanup after startup, independent of interpreter launch time.
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "The child must actually start before testing cleanup"
            start.touch()
            return process
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise

    monkeypatch.setattr(narrate.subprocess, "Popen", started_cli)
    with pytest.raises(RuntimeError, match="timed out"):
        narrate._call_codex_cli("", "System", "Event", timeout=0.5)
    time.sleep(0.7)
    assert not marker.exists(), "A child must not outlive the narrator deadline"


def test_cli_child_hooks_cannot_reenter_playback(tmp_path, monkeypatch):
    """Force lifecycle hooks from a child even if CLI hook suppression regresses."""
    root = Path(__file__).resolve().parents[1] / "code-gossip"
    marker = tmp_path / "playback.txt"
    # Import the real adapter, but use a disposable runtime that records playback.
    runtime = tmp_path / "runtime"
    (runtime / "engine").mkdir(parents=True)
    (runtime / "engine/play.sh").write_text(f'echo played >> "{marker}"\n')
    events = ["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"]
    source = f'''import importlib.util,json,sys,subprocess
from pathlib import Path
spec=importlib.util.spec_from_file_location("adapter", {str(root / "hooks/codex.py")!r})
adapter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
for event in {events!r}:
    adapter.dispatch({{"hook_event_name":event}}, Path({str(runtime)!r}))
    # Shared playback must exit before reading stdin or resolving dependencies.
    result=subprocess.run(["/bin/bash", "-x", {str(root / "engine/play.sh")!r}, "stop"],
                          input="{{}}", text=True, capture_output=True, timeout=1)
    assert result.returncode == 0
    assert "STDIN_DATA=" not in result.stderr
print("Updated the code.")
'''
    fake_cli(tmp_path, monkeypatch, source)
    assert narrate._call_codex_cli("", "System", "Event") == "Updated the code."
    assert not marker.exists()
    # Positive control: normal agent events still dispatch to the runtime.
    monkeypatch.delenv("CODE_GOSSIP_NARRATOR", raising=False)
    codex.dispatch({"hook_event_name": "Stop"}, runtime)
    assert marker.read_text() == "played\n"


def test_playback_guard_exits_without_waiting_for_hook_stdin():
    play = Path(__file__).resolve().parents[1] / "code-gossip/engine/play.sh"
    with subprocess.Popen(["/bin/bash", str(play), "stop"], stdin=subprocess.PIPE,
                          env=dict(os.environ, CODE_GOSSIP_NARRATOR="1")) as process:
        assert process.wait(timeout=1) == 0
