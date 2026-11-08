"""Real daemon processes and sockets, without models, downloads, or personal state."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

import pytest

import kokoro_server as daemon


def wait_for(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.02)
    pytest.fail('Timed out waiting for isolated Kokoro process')


@pytest.fixture
def runtime():
    # macOS limits Unix socket paths to 104 bytes; pytest's default base is longer.
    with tempfile.TemporaryDirectory(prefix='cg-kokoro-', dir='/tmp') as directory:
        root = Path(directory)
        source = Path(__file__).resolve().parents[1] / 'code-gossip'
        (root / 'engine').mkdir()
        (root / 'state').mkdir()
        for name in ('paths.py', 'engine/narrate.py', 'engine/kokoro_server.py'):
            shutil.copy2(source / name, root / name)
        script = root / 'daemon.py'
        script.write_text('''import os, time
from paths import STATE
from engine import kokoro_server as daemon
with (STATE / 'launches').open('a') as output:
    output.write(str(os.getpid()) + '\\n')
# Keep the socket absent long enough to exercise overlapping startup callers.
time.sleep(.3)
daemon.model._load_model = lambda: object()
daemon.model._load_voice = lambda voice: None
try:
    daemon.main()
finally:
    (STATE / ('exited-' + str(os.getpid()))).touch()
''')
        helper = root / 'helper.py'
        helper.write_text('''import os, sys, time
from pathlib import Path
from engine import narrate
narrate.KOKORO_VENV = Path(sys.executable)
narrate.KOKORO_DAEMON = Path(__file__).with_name('daemon.py')
(narrate.STATE / ('ready-' + str(os.getpid()))).touch()
if 'wait' in sys.argv:
    while not (narrate.STATE / 'go').exists():
        time.sleep(.01)
if 'miss-health' in sys.argv:
    request = narrate._kokoro_request
    missed = False
    def once(*args, **kwargs):
        global missed
        if not missed:
            missed = True
            return None
        return request(*args, **kwargs)
    narrate._kokoro_request = once
print(narrate._ensure_kokoro_daemon(), flush=True)
''')
        processes = []

        def start(name, *args):
            process = subprocess.Popen([sys.executable, str(root / name), *args],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
            return process

        def health():
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(.5)
                    client.connect(str(root / 'state/kokoro.sock'))
                    client.sendall(b'{"cmd":"health"}\n')
                    return json.loads(client.recv(4096)).get('ok')
            except (OSError, ValueError):
                return False

        def launches():
            path = root / 'state/launches'
            return [int(pid) for pid in path.read_text().splitlines()] if path.exists() else []

        try:
            yield root, start, health, launches
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            # Helpers launch detached daemons, which still belong to this fixture.
            for pid in launches():
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for process in processes:
                process.communicate(timeout=5)
            if launches():
                wait_for(lambda: not (root / 'state/kokoro.sock').exists())


def test_concurrent_helpers_launch_one_daemon(runtime):
    root, start, health, launches = runtime
    helpers = [start('helper.py', 'wait') for _ in range(4)]
    wait_for(lambda: len(list((root / 'state').glob('ready-*'))) == len(helpers))
    (root / 'state/go').touch()
    for process in helpers:
        out, err = process.communicate(timeout=12)
        assert process.returncode == 0, err
        assert out.strip() == 'True', err
    assert len(launches()) == 1, 'Concurrent checks must share one daemon launch'
    assert health()


def test_duplicate_daemon_cannot_replace_live_socket_and_restart_recovers(runtime):
    root, start, health, launches = runtime
    sock = root / 'state/kokoro.sock'
    first = start('daemon.py')
    wait_for(health)
    identity = sock.stat().st_ino
    duplicate = start('daemon.py')
    out, err = duplicate.communicate(timeout=5)
    assert duplicate.returncode == 0, err
    assert first.poll() is None
    assert sock.stat().st_ino == identity
    assert health(), 'A duplicate exiting must leave the live daemon reachable'
    first.terminate()
    first.communicate(timeout=5)
    assert not sock.exists()
    assert (root / 'state/kokoro.lock').exists(), 'Lock files must keep their inode'
    sock.write_text('stale socket')
    replacement = start('daemon.py')
    wait_for(health)
    assert replacement.poll() is None
    assert sock.is_socket()


def test_startup_lock_has_a_bounded_wait(runtime):
    root, start, health, launches = runtime
    with (root / 'state/kokoro-start.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = start('helper.py')
        out, err = blocked.communicate(timeout=8)
        assert blocked.returncode == 0, err
        assert out.strip() == 'False'
        assert not launches()
    # A timed-out caller does not poison future starts.
    retry = start('helper.py')
    out, err = retry.communicate(timeout=8)
    assert retry.returncode == 0, err
    assert out.strip() == 'True'
    assert health()


def test_failed_health_check_does_not_unlink_live_daemon(runtime):
    root, start, health, launches = runtime
    first = start('daemon.py')
    wait_for(health)
    sock = root / 'state/kokoro.sock'
    identity = sock.stat().st_ino
    helper = start('helper.py', 'miss-health')
    out, err = helper.communicate(timeout=8)
    assert helper.returncode == 0, err
    assert out.strip() == 'True'
    # Let the duplicate child exit so cleanup is also covered.
    wait_for(lambda: len(launches()) == 2)
    wait_for(lambda: (root / 'state' / ('exited-' + str(launches()[1]))).exists())
    assert first.poll() is None
    assert sock.stat().st_ino == identity
    assert health()


def test_cleanup_preserves_replacement_socket(tmp_path, monkeypatch):
    sock = tmp_path / 'kokoro.sock'
    sock.touch()
    bound = sock.stat()
    identity = (bound.st_dev, bound.st_ino)
    # Retain the old inode to rule out filesystem inode reuse in this test.
    sock.rename(tmp_path / 'old.sock')
    sock.touch()
    monkeypatch.setattr(daemon, 'SOCK_PATH', str(sock))
    daemon.cleanup(identity)
    assert sock.exists(), 'An old daemon must not unlink its replacement'
    current = sock.stat()
    daemon.cleanup((current.st_dev, current.st_ino))
    assert not sock.exists()
