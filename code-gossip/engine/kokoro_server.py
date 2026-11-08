#!/usr/bin/env python3
"""Kokoro TTS daemon — keeps model warm, serves speech over Unix socket.

Loads the Kokoro-82M model once on startup, then serves TTS requests with
~100-200ms latency instead of 3-5s cold starts. Auto-shuts down after 10
minutes idle.

Socket: ~/.code-gossip/state/kokoro.sock
Protocol: newline-delimited JSON over Unix stream socket.

Requests:
  {"cmd": "health"}
  {"cmd": "speak", "text": "...", "voice": "af_heart", "volume": 100}

Responses:
  {"ok": true, ...}
  {"ok": false, "error": "..."}

Setup:
  python3 -m venv ~/.code-gossip/state/.venv
  ~/.code-gossip/state/.venv/bin/pip install kokoro soundfile

Run:
  ~/.code-gossip/state/.venv/bin/python kokoro_server.py
"""

import json
import os
import re
import sys
from pathlib import Path


import signal
import socketserver
import subprocess
import tempfile
import threading
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import STATE

SOCK_PATH = str(STATE / "kokoro.sock")
IDLE_TIMEOUT = 600  # 10 minutes


def download_progress(report):
    """A quiet tqdm adapter for both HTTP and Xet's buffered transfers."""
    from tqdm import tqdm

    class Progress(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs.pop("name", None)
            kwargs["disable"] = True
            self.transferred = 0
            super().__init__(*args, **kwargs)
            self.publish()

        def publish(self):
            report(completed=self.n, total=self.total, transferred=self.transferred)

        def update(self, n=1):
            # tqdm skips counters when disabled; retain them without terminal output.
            self.n += n
            self.publish()

        def update_transfer(self, n):
            # Xet can receive bytes before reconstructing any of the model file.
            self.transferred += n
            self.publish()

        def set_transfer_postfix_str(self, text, refresh=True):
            # Xet's aggregate progress protocol also sends terminal-only rate text.
            pass

        def refresh(self, *args, **kwargs):
            self.publish()

    return Progress


class ModelManager:
    """Prepare the shared model and requested voices without blocking health calls."""

    def __init__(self):
        self.pipelines = {}
        self.weights = None
        self.voices = set()
        self.requested = set()
        self.lock = threading.RLock()
        self.loading = False
        self.error = False
        self.progress = {"state": "idle", "message": "Kokoro model has not loaded yet."}
        self.last_activity = time.time()

    def status(self, voices=()):
        with self.lock:
            ready = self.weights is not None and set(voices).issubset(self.voices)
            progress = ({"state": "ready", "message": "Kokoro model and selected voices are ready."}
                        if ready else dict(self.progress))
            return {"ok": True, "ready": ready, "loaded": sorted(self.pipelines),
                    "voices": sorted(self.voices), "idle": int(self.idle_seconds()), **progress}

    def prepare(self, voices=(), retry=False):
        if not isinstance(voices, (list, tuple)) or any(
                not isinstance(v, str) or not re.fullmatch(r"[ab][fm]_[a-z0-9]+", v) for v in voices):
            raise ValueError("Invalid Kokoro voices")
        with self.lock:
            self.touch()
            self.requested.update(voices)
            if not self.loading and (not self.error or retry):
                if self.weights is None or self.requested - self.voices:
                    self.error = False
                    self.loading = True
                    self.progress = {"state": "loading", "message": "Preparing Kokoro model…"}
                    threading.Thread(target=self._prepare, daemon=True).start()
            return self.status(voices)

    def _stage(self, state, message, **details):
        with self.lock:
            self.progress = {"state": state, "message": message, **details}
            self.touch()

    def _download(self, filename):
        from huggingface_hub import hf_hub_download
        self._stage("downloading", "Downloading " + filename, file=filename,
                    completed=0, total=None, transferred=0)

        def report(**values):
            self._stage("downloading", "Downloading " + filename, file=filename, **values)

        return hf_hub_download(repo_id="hexgrad/Kokoro-82M", filename=filename,
                               tqdm_class=download_progress(report))

    def _load_model(self):
        from kokoro import KModel
        config = self._download("config.json")
        weights = self._download(KModel.MODEL_NAMES["hexgrad/Kokoro-82M"])
        self._stage("loading", "Loading Kokoro model into memory…")
        return KModel(repo_id="hexgrad/Kokoro-82M", config=config, model=weights).eval()

    def _load_voice(self, voice):
        from kokoro import KPipeline
        path = self._download("voices/" + voice + ".pt")
        self._stage("loading", "Loading Kokoro voice " + voice + "…")
        lang = voice[0]
        # Downloads must not block speech with a voice that is already ready.
        with inference_lock:
            if lang not in self.pipelines:
                self.pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M",
                                                model=self.weights)
            pipeline = self.pipelines[lang]
            # Cache under the voice ID so synthesis never starts a hidden download.
            pipeline.voices[voice] = pipeline.load_voice(path)

    def _prepare(self):
        try:
            if self.weights is None:
                weights = self._load_model()
                with self.lock:
                    self.weights = weights
            while True:
                with self.lock:
                    pending = sorted(self.requested - self.voices)
                    if not pending:
                        self.loading = False
                        self._stage("ready", "Kokoro model and selected voices are ready.")
                        return
                for voice in pending:
                    self._load_voice(voice)
                    with self.lock:
                        self.voices.add(voice)
        except Exception:
            import traceback
            traceback.print_exc()
            with self.lock:
                self.loading = False
                self.error = True
                # Do not expose signed download URLs, tokens, or local paths.
                self._stage("error", "Kokoro model or voice could not load. Check your connection and retry model loading.")

    def touch(self):
        self.last_activity = time.time()

    def idle_seconds(self):
        return time.time() - self.last_activity


model = ModelManager()
# Serialize inference (model is not thread-safe)
inference_lock = threading.Lock()


class Handler(socketserver.StreamRequestHandler):

    def handle(self):
        try:
            line = self.rfile.readline().decode("utf-8").strip()
            if not line:
                return
            req = json.loads(line)
            cmd = req.get("cmd", "")

            if cmd == "health":
                model.touch()
                resp = model.status(req.get("voices", []))
            elif cmd == "prepare":
                resp = model.prepare(req.get("voices", []), retry=req.get("retry") is True)
            elif cmd == "speak":
                resp = self._speak(req)
            else:
                resp = {"ok": False, "error": f"unknown command: {cmd}"}

            self.wfile.write(json.dumps(resp).encode() + b"\n")
            self.wfile.flush()
        except Exception as e:
            try:
                self.wfile.write(
                    json.dumps({"ok": False, "error": str(e)}).encode() + b"\n"
                )
                self.wfile.flush()
            except Exception:
                pass

    def _speak(self, req):
        text = req.get("text", "")
        voice = req.get("voice", "af_heart")
        volume = req.get("volume", 100)

        if not text:
            return {"ok": False, "error": "no text"}

        status = model.prepare([voice])
        if not status["ready"]:
            return {**status, "ok": False, "error": status["message"]}

        import numpy as np
        lang_code = voice[0]

        # Serialize inference — model is not thread-safe
        with inference_lock:
            pipeline = model.pipelines[lang_code]
            chunks = []
            for _gs, _ps, audio in pipeline(text, voice=voice):
                if audio is not None:
                    chunks.append(audio)

        if not chunks:
            return {"ok": False, "error": "no audio generated"}

        combined = np.concatenate(chunks)
        pcm = (np.clip(combined, -1.0, 1.0) * 32767).astype(np.int16)

        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="soundbar_kokoro_")
        os.close(fd)
        try:
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm.tobytes())

            vol_str = f"{volume // 100}.{volume % 100:02d}"
            subprocess.run(
                ["afplay", "-v", vol_str, tmp],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            return {"ok": True}
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def idle_watcher(server):
    """Shut down server after idle timeout."""
    while True:
        time.sleep(30)
        if not model.loading and model.idle_seconds() > IDLE_TIMEOUT:
            print("Idle timeout — shutting down.")
            server.shutdown()
            return


def cleanup():
    try:
        os.unlink(SOCK_PATH)
    except OSError:
        pass


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    if "--check" in sys.argv:
        try:
            from kokoro import KPipeline  # noqa: F401
            print(json.dumps({"ok": True, "message": "Kokoro packages are installed; model readiness is checked separately."}))
        except ImportError:
            print(json.dumps({
                "ok": False,
                "message": "Kokoro not installed. Run:\n"
                "  python3 -m venv ~/.code-gossip/state/.venv\n"
                "  ~/.code-gossip/state/.venv/bin/pip install kokoro soundfile"
            }))
        return

    # Clean up stale socket
    cleanup()

    def _shutdown(signum, frame):
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    # Model preparation continues independently of short-lived preview requests.
    model.prepare()

    server = UnixServer(SOCK_PATH, Handler)
    os.chmod(SOCK_PATH, 0o600)

    # Start idle watcher
    threading.Thread(target=idle_watcher, args=(server,), daemon=True).start()

    print(f"Kokoro daemon: {SOCK_PATH} (PID {os.getpid()})")
    try:
        server.serve_forever()
    finally:
        cleanup()
    print("Kokoro daemon stopped.")


if __name__ == "__main__":
    main()
