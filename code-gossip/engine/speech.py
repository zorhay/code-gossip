"""Speech delivery and engine checks; no narration or trajectory dependencies."""
import json
import logging
import os
import socket as sock_mod
import subprocess
import tempfile
import time
from paths import STATE, ENGINE, executable

_log = logging.getLogger("speech")

TTS_ENGINES = {
    "say": {
        "name": "macOS Say",
        "description": "Built-in macOS TTS. No setup needed.",
    },
    "kokoro": {
        "name": "Kokoro",
        "description": "Local neural TTS via background daemon. Keeps model warm for fast speech.",
    },
}

KOKORO_VOICES = [
    {"id": "af_heart", "name": "Heart", "gender": "female"},
    {"id": "af_bella", "name": "Bella", "gender": "female"},
    {"id": "af_nicole", "name": "Nicole", "gender": "female"},
    {"id": "af_sarah", "name": "Sarah", "gender": "female"},
    {"id": "af_sky", "name": "Sky", "gender": "female"},
    {"id": "am_adam", "name": "Adam", "gender": "male"},
    {"id": "am_michael", "name": "Michael", "gender": "male"},
    {"id": "bf_emma", "name": "Emma (British)", "gender": "female"},
    {"id": "bf_isabella", "name": "Isabella (British)", "gender": "female"},
    {"id": "bm_george", "name": "George (British)", "gender": "male"},
    {"id": "bm_lewis", "name": "Lewis (British)", "gender": "male"},
]


def speak(text, engine, voice, volume):
    """Speak text via configured TTS engine."""
    _log.info("speak: engine=%s voice=%s volume=%s", engine, voice, volume)
    if engine == "kokoro":
        return speak_kokoro(text, voice, volume)
    else:
        return speak_say(text, voice, volume)


def speak_say(text, voice, volume):
    """Speak text via macOS TTS with volume control."""
    vol_str = f"{volume // 100}.{volume % 100:02d}"
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".aiff", prefix="soundbar_narr_")
        os.close(fd)
        subprocess.run(
            [executable("say") or "say", "-v", voice, "-r", "190", text, "-o", tmp],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10, check=True,
        )
        subprocess.run(
            [executable("afplay") or "afplay", "-v", vol_str, tmp],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=30, check=True,
        )
        return True
    except Exception:
        return False
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


KOKORO_SOCK = STATE / "kokoro.sock"
KOKORO_VENV = STATE / ".venv" / "bin" / "python"
KOKORO_DAEMON = ENGINE / "kokoro_server.py"


def _kokoro_request(cmd, timeout=30, **kwargs):
    """Send a request to the Kokoro daemon. Returns response dict or None."""
    _log.debug("kokoro request: cmd=%s timeout=%s", cmd, timeout)
    s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
    try:
        s.connect(str(KOKORO_SOCK))
        s.settimeout(timeout)
        req = json.dumps({"cmd": cmd, **kwargs})
        s.sendall(req.encode() + b"\n")
        resp = s.makefile().readline()
        result = json.loads(resp) if resp else None
        _log.debug("kokoro response: %s", result)
        return result
    except Exception as e:
        _log.error("kokoro request failed: cmd=%s err=%s", cmd, e)
        return None
    finally:
        s.close()


def _ensure_kokoro_daemon():
    """Start Kokoro daemon if not running. Returns True if daemon is available."""
    _log.debug("ensure_kokoro_daemon: sock=%s exists=%s", KOKORO_SOCK, KOKORO_SOCK.exists())

    # Already running?
    if KOKORO_SOCK.exists():
        resp = _kokoro_request("health", timeout=3)
        if resp and resp.get("ok"):
            _log.debug("daemon already running")
            return True
        # Stale socket
        _log.debug("stale socket, removing")
        try:
            KOKORO_SOCK.unlink()
        except OSError:
            pass

    # Venv must exist
    if not KOKORO_VENV.exists():
        _log.error("venv python missing: %s", KOKORO_VENV)
        return False

    # Start daemon (detached)
    daemon_cmd = [str(KOKORO_VENV), str(KOKORO_DAEMON)]
    _log.info("starting kokoro daemon: %s", daemon_cmd)

    # Capture daemon stderr to a log file for debugging
    daemon_log = STATE / "kokoro_daemon.log"
    try:
        daemon_err = open(daemon_log, "a")
    except Exception:
        daemon_err = subprocess.DEVNULL

    subprocess.Popen(
        daemon_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=daemon_err,
        start_new_session=True,
    )

    # Wait for socket — daemon creates it before model finishes loading
    for i in range(50):
        time.sleep(0.1)
        if KOKORO_SOCK.exists():
            resp = _kokoro_request("health", timeout=3)
            if resp and resp.get("ok"):
                _log.info("daemon started after %.1fs", (i + 1) * 0.1)
                return True
    _log.error("daemon failed to start within 5s. Check %s", daemon_log)
    return False


def speak_kokoro(text, voice, volume):
    """Speak text via Kokoro daemon (auto-starts if needed).

    Does NOT fall back to macOS say — if kokoro fails, it fails silently.
    Callers (play.sh hooks) should not degrade to a different engine
    without the user knowing. The UI shows engine status so the user
    can switch manually if kokoro is broken.
    """
    _log.info("speak_kokoro: voice=%s volume=%s text=%r", voice, volume, text[:60])
    if not _ensure_kokoro_daemon():
        _log.error("speak_kokoro: daemon unavailable, skipping")
        return False

    resp = _kokoro_request("speak", timeout=30, text=text, voice=voice, volume=volume)
    if not resp or not resp.get("ok"):
        _log.error("speak_kokoro: speak failed: %s", resp)
    return bool(resp and resp.get("ok"))


def _read_integrations():
    """Read integrations.json for cached state."""
    try:
        return json.loads((STATE / "integrations.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_kokoro():
    """Check if Kokoro TTS is available."""
    if not KOKORO_VENV.exists():
        # Check integrations for python detection info
        data = _read_integrations()
        py_info = data.get("kokoro_python")
        if py_info and not py_info.get("ok"):
            return {"ok": False, "message": py_info.get("message", "No compatible Python found.")}
        return {
            "ok": False,
            "message": "Kokoro not installed. Use the control panel to install, "
            "or set up manually with a compatible Python (3.9-3.11).",
        }

    if KOKORO_SOCK.exists():
        resp = _kokoro_request("health", timeout=3)
        if resp and resp.get("ok"):
            ready = resp.get("ready", False)
            if ready:
                return {"ok": True, "message": "Kokoro daemon running, model loaded."}
            return {"ok": True, "message": "Kokoro daemon running, model loading..."}

    # Daemon not running — check if kokoro package is installed
    try:
        result = subprocess.run(
            [str(KOKORO_VENV), "-c", "import kokoro"],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0:
            return {"ok": True, "message": "Kokoro installed. Daemon will auto-start on first use."}
        return {
            "ok": False,
            "message": "Kokoro not installed in venv. Use the control panel to reinstall.",
        }
    except Exception as e:
        return {"ok": False, "message": f"Error checking venv: {e}"}
