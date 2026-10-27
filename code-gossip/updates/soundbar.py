"""Soundbar lifecycle and verification for update and recovery workflows."""

import json
import os
import subprocess
import time
from urllib.request import ProxyHandler, build_opener
from urllib.error import HTTPError, URLError

import installer
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .entities import Installation
from .errors import UpdateError
from .installation import install_environment
from .storage import installed_version, read_json


def restart_and_verify(paths: UpdatePaths, record: Installation, port: int, expected: str,
                       config: UpdateConfig = DEFAULT_CONFIG) -> None:
    stop_panel(paths, config)
    process = start_panel(paths, record, port)
    if wait_for_health(paths, process, port, expected, config):
        return
    stop_failed_start(process, config)
    raise UpdateError("Updated Soundbar failed its health check. See state/panel.log.")


def start_panel(paths: UpdatePaths, record: Installation, port: int) -> subprocess.Popen:
    paths.panel_log.parent.mkdir(exist_ok=True)
    with paths.panel_log.open("a") as log:
        return subprocess.Popen(
            [record.python, "-B", str(paths.root / "soundbar/server.py")],
            cwd=paths.root, env={**install_environment(record), "PORT": str(port)},
            start_new_session=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        )


def wait_for_health(paths: UpdatePaths, process: subprocess.Popen, port: int, expected: str,
                    config: UpdateConfig) -> bool:
    deadline = time.monotonic() + config.panel_start_timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            health = panel_request(port, "/api/health", config)
            if (health.get("app") == "code-gossip" and health.get("root") == str(paths.root.resolve())
                    and health.get("version") == expected and installed_version(paths.root) == expected):
                return True
        except (OSError, ValueError):
            pass
        time.sleep(config.panel_start_poll_interval)
    return False


def stop_failed_start(process: subprocess.Popen, config: UpdateConfig) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=config.panel_terminate_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def panel_port(paths: UpdatePaths, config: UpdateConfig = DEFAULT_CONFIG) -> int:
    return int(read_json(paths.panel_state).get("port", os.environ.get("PORT", config.panel_default_port)))


def panel_request(port: int, endpoint: str, config: UpdateConfig = DEFAULT_CONFIG) -> dict:
    with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}{endpoint}", timeout=config.panel_request_timeout) as response:
        return json.load(response)


def ensure_panel_idle(paths: UpdatePaths, port: int, config: UpdateConfig = DEFAULT_CONFIG) -> bool:
    root = paths.root
    try:
        health = panel_request(port, "/api/health", config)
    except HTTPError as exc:
        raise UpdateError("Soundbar's port is occupied by another application.") from exc
    except URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            return False
        raise UpdateError("Could not verify the service on Soundbar's port. Close it before updating.") from exc
    except (ValueError, TimeoutError) as exc:
        raise UpdateError("Could not verify the service on Soundbar's port. Close it before updating.") from exc
    except OSError:
        return False
    if not isinstance(health, dict) or health.get("app") != "code-gossip" or health.get("root") != str(root.resolve()):
        raise UpdateError("Soundbar's port is occupied by another application or installation.")
    if panel_request(port, "/api/setup", config).get("installing"):
        raise UpdateError("Wait for Kokoro installation to finish before updating.")
    return True


def stop_panel(paths: UpdatePaths, config: UpdateConfig = DEFAULT_CONFIG) -> None:
    root = paths.root
    pid_file = paths.panel_pid
    try:
        pid = int(pid_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        return
    if installer.stop_process(pid, root / "soundbar/server.py"):
        deadline = time.monotonic() + config.panel_stop_timeout
        while time.monotonic() < deadline:
            result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
            if result.returncode or result.stdout.strip().startswith("Z"):
                break
            time.sleep(config.panel_stop_poll_interval)
        else:
            raise UpdateError("Soundbar did not stop. Close it and retry.")
    if pid_file.exists() and pid_file.read_text().strip() == str(pid):
        pid_file.unlink()
