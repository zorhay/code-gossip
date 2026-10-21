#!/usr/bin/env python3
"""Short, stateful melodies for manifest-driven generated effects."""

import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import STATE, executable
from engine.playback_gate import acquire_lock, read_json

IDLE_SECONDS = 120
PHRASES = {"note", "rise", "fall", "question", "resolve"}


def scale_notes(settings):
    """Expand pitch classes into a bounded MIDI-note palette."""
    root = settings["root"]
    low, high = settings["range"]
    scale = settings["scale"]
    if (any(type(n) is not int for n in [root, low, high, *scale])
            or not 0 <= root <= 127 or not 0 <= low < high <= 127
            or not scale or any(not 0 <= n < 12 for n in scale)):
        raise ValueError("Invalid melody scale or range")
    notes = [note for note in range(low, high + 1) if (note - root) % 12 in scale]
    if len(notes) < 3:
        raise ValueError("Melodies need at least three notes")
    return notes


def choose_note(notes, history, rng, candidates=None):
    """Favor neighboring scale steps, fresh pitches, and recovery after leaps."""
    candidates = list(notes if candidates is None else candidates)
    previous = history[-1] if history else None
    if previous in candidates and len(candidates) > 1:
        candidates.remove(previous)
    weights = []
    for note in candidates:
        if previous is None:
            distance = abs(notes.index(note) - (len(notes) - 1) / 2)
            weight = 1 / (1 + distance)
        else:
            distance = abs(notes.index(note) - notes.index(previous))
            weight = {0: 0.1, 1: 12, 2: 5, 3: 1.5}.get(distance, 0.3)
            if note in history[-4:]:
                weight *= 0.2
            if len(history) > 1:
                leap = previous - history[-2]
                if abs(leap) >= 5 and leap * (note - previous) < 0:
                    weight *= 2
        weights.append(weight)
    return rng.choices(candidates, weights=weights, k=1)[0]


def compose(settings, spec, history=(), rng=None):
    """Compose a cue; only the resolve phrase gets a fifth-to-tonic ending."""
    rng = rng or random.SystemRandom()
    notes = scale_notes(settings)
    history = [n for n in history if type(n) is int and n in notes][-4:]
    phrase = spec.get("phrase", "note")
    if phrase not in PHRASES:
        raise ValueError("Unknown melody phrase")
    if phrase == "resolve":
        cadences = [(fifth, tonic) for tonic in notes
                    if (tonic - settings["root"]) % 12 == 0
                    for fifth in (tonic - 5, tonic + 7) if fifth in notes]
        if not cadences:
            raise ValueError("Resolution needs a tonic and fifth in range")
        previous = history[-1] if history else notes[len(notes) // 2]
        weights = [1 / (1 + abs(fifth - previous)) for fifth, _ in cadences]
        return list(rng.choices(cadences, weights=weights, k=1)[0])
    def followers(first):
        return [n for n in notes
                if (n > first if phrase == "rise" else n < first)
                and not ((first - settings["root"]) % 12 == 7
                         and (n - settings["root"]) % 12 == 0)]

    # Keep the completion cadence out of every possible work phrase.
    candidates = [n for n in notes if followers(n)] if phrase in {"rise", "fall"} else notes
    first = choose_note(notes, history, rng, candidates)
    if phrase == "question":
        return [first, first]
    if phrase in {"rise", "fall"}:
        return [first, choose_note(notes, history + [first], rng, followers(first))]
    return [first]


def next_notes(settings, spec, identity, *, preview=False, state_dir=None, rng=None):
    """Share recent notes across hooks; previews have an independent history."""
    state_dir = STATE / "melody" if state_dir is None else Path(state_dir)
    key = hashlib.sha256(json.dumps([identity, settings, preview], sort_keys=True).encode()).hexdigest()
    try:
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state_dir / "lock").open("a") as lock:
            acquire_lock(lock)
            now = time.clock_gettime(time.CLOCK_MONOTONIC)
            path = state_dir / "state.json"
            state = {k: v for k, v in read_json(path).items()
                     if isinstance(v, dict) and isinstance(v.get("time"), (int, float))
                     and 0 <= now - v["time"] < IDLE_SECONDS
                     and isinstance(v.get("notes"), list)}
            history = state.get(key, {}).get("notes", [])
            selected = compose(settings, spec, history, rng)
            state[key] = {"time": now, "notes": (history + selected)[-4:]}
            state = dict(sorted(state.items(), key=lambda item: item[1]["time"])[-64:])
            temporary = state_dir / "state.tmp"
            temporary.write_text(json.dumps(state))
            os.replace(temporary, path)
            return selected
    except OSError:
        # A locked or unwritable state directory must not silence hook audio.
        return compose(settings, spec, rng=rng)


def sox_args(notes, spec, volume):
    """Render quiet sine envelopes and reverb at musical pitches."""
    duration = float(spec["duration"])
    gain = float(spec["gain"])
    attack = float(spec["attack"])
    release = float(spec["release"])
    reverb = float(spec["reverb"])
    volume = float(volume)
    if (not all(math.isfinite(n) for n in (duration, gain, attack, release, reverb, volume))
            or not 0.05 <= duration <= 3 or not 0 <= gain <= 1
            or not 0 <= attack <= duration or not 0 <= release or attack + release > duration + 1e-9
            or not 0 <= reverb <= 100 or not 0 <= volume <= 1):
        raise ValueError("Invalid melody envelope or volume")
    # duration, attack, and release describe the entire cue, not each pulse.
    length = duration / len(notes)
    args = []
    for i, note in enumerate(notes):
        if i:
            args.append(":")
        frequency = 440 * 2 ** ((note - 69) / 12)
        args.extend(["synth", f"{length:.6f}", "sine", f"{frequency:.6f}",
                     "vol", str(gain), "fade", f"{attack / len(notes):.6f}",
                     f"{length:.6f}", f"{release / len(notes):.6f}",
                     "reverb", str(reverb), "vol", str(volume)])
    return args


def main():
    try:
        manifest, layer, profile, event, volume, *options = sys.argv[1:]
        player = executable("play")
        if not player:
            return 1
        data = json.loads(Path(manifest).read_text())[layer][profile]
        spec = data["events"][event]["melody"]
        # Validate synthesis before advancing the shared history.
        sox_args([60], spec, volume)
        notes = next_notes(data["melody"], spec, [layer, profile], preview="--preview" in options)
        subprocess.run([player, "-qn", *sox_args(notes, spec, volume)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=10)
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
