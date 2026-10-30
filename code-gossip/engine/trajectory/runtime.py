#!/usr/bin/env python3
"""Composition roots for ingestion, background summarization, and speech.

Hooks call observe(); provider and audio modules load only in worker processes.
"""
import fcntl
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT
from engine.trajectory.contracts import Observation
from engine.trajectory.store import Store


def settings(root):
    result = {}
    for name in ("config.defaults.json", "config.json"):
        try:
            data = json.loads((Path(root) / "configs" / name).read_text())
            if isinstance(data, dict):
                result.update(data)
        except (OSError, ValueError):
            pass
    return result


def enabled(config):
    return config.get("voice_profile") == "narrator" and (config.get("voice_on") is True or config.get("soundbar_mode") == "ai")


def internal():
    return os.environ.get("CODE_GOSSIP_INTERNAL") == "1"


def start(root, command, *args):
    python = settings(root).get("python3_path") or sys.executable
    if not Path(python).is_file() or not os.access(python, os.X_OK):
        python = sys.executable
    subprocess.Popen([python, str(Path(__file__).resolve()), command, str(root), *map(str, args)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)


def observe(agent, event, data, root=ROOT, launch=True):
    """Collection is independent of sound classification, suppression, and locks."""
    if internal() or not enabled(settings(root)):
        return None
    observation = Observation.from_hook(agent, event, data)
    if observation is None:
        return None
    store = Store(Path(root) / "state" / "trajectories.sqlite3")
    try:
        sid = store.collect(observation)
    finally:
        store.close()
    if launch:
        start(root, "work", sid)
    return sid


def lock(root, name):
    directory = Path(root) / "state" / "trajectory-locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (directory / name).open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def work(root, sid):
    from engine.llm import client
    from engine.narrate import style_prompt
    from engine.trajectory.processor import Processor

    handle = lock(root, f"session-{sid}.lock")
    if handle is None:
        return
    store = Store(Path(root) / "state" / "trajectories.sqlite3")
    generation = store.generation(sid)
    failures = 0
    maintenance_due = 0
    try:
        store.prune()
        if not store.session(sid):
            return
        while True:
            config = settings(root)
            if not enabled(config):
                break
            generation = store.generation(sid)
            if time.time() >= maintenance_due:
                store.limit_payloads(sid)
                maintenance_due = time.time() + 60
            processor = Processor(store, client(config), style_prompt(config.get("narrator_style", "pair_programmer")))
            try:
                changed = processor.step(sid, time.time())
            except Exception as error:
                logging.warning("Trajectory generation failed (%s); evidence remains pending", type(error).__name__)
                failures += 1
                if failures >= 3:
                    break
                time.sleep(failures)
                continue
            failures = 0
            if changed == "narration":
                start(root, "deliver")
            if changed:
                continue
            if not store.waiting(sid):
                break
            time.sleep(.1)  # Own the quiet timer so the last batch needs no further hook.
    finally:
        handle.close()
        # A collector may have committed after our last idle check while its worker lost the lock.
        wake = store.session(sid) and store.generation(sid) != generation
        store.close()
        if wake:
            start(root, "work", sid)


def deliver(root):
    from engine.speech import speak

    handle = lock(root, "speaker.lock")
    if handle is None:
        return
    store = Store(Path(root) / "state" / "trajectories.sqlite3")
    try:
        store.recover_delivery(time.time())
        while True:
            item = store.next_delivery()
            if not item:
                break
            config = settings(root)
            if not enabled(config) or not config.get("voice_on") or not config.get("voice_volume", 100):
                store.delivery_status(item["id"], "muted", time.time())
                continue
            if not store.delivery_current(item):
                store.delivery_status(item["id"], "superseded", time.time())
                continue
            if store.already_delivered(item["session_id"], item["text"]):
                store.delivery_status(item["id"], "silent", time.time())
                continue
            if store.session(item["session_id"])["agent"] == "codex" and config.get("codex_permission_sound_on") is False:
                if any(e["event"] == "PermissionRequest" for e in store.batch_events(item["batch_id"])):
                    store.delivery_status(item["id"], "muted", time.time())
                    continue
            gap = max(0, min(10000, float(config.get("voice_cooldown_ms", 3000)))) / 1000
            if item["urgent"]:
                gap = min(gap, 1)
            if config.get("sound_spacing_on") is not False and time.time() - store.last_delivery() < gap:
                time.sleep(.1)
                continue
            store.delivery_status(item["id"], "playing", time.time())
            engine = config.get("tts_engine", "say")
            voice = config.get("kokoro_voice", "af_heart") if engine == "kokoro" else config.get("voice_main", "Tara")
            ok = speak(item["text"], engine, voice, int(config.get("voice_volume", 100)))
            store.delivery_status(item["id"], "completed" if ok else "failed", time.time())
    finally:
        handle.close()
        wake = store.pending_delivery_generation()
        store.close()
        if wake:
            start(root, "deliver")


def main():
    command, root = sys.argv[1:3]
    root = Path(root)
    (root / "state").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=root / "state" / "trajectory.log", level=logging.WARNING)
    try:
        if command == "work":
            work(root, int(sys.argv[3]))
        elif command == "deliver":
            deliver(root)
        elif command == "inspect":
            store = Store(root / "state" / "trajectories.sqlite3")
            try:
                print(json.dumps(store.export(int(sys.argv[3])), ensure_ascii=False, indent=2))
            finally:
                store.close()
    except (OSError, ValueError, sqlite3.Error):
        logging.exception("Trajectory runtime failed")


if __name__ == "__main__":
    main()
