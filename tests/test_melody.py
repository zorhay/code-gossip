"""Musical constraints, cross-process history, and hook dispatch."""

from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from engine import melody

ROOT = Path(__file__).resolve().parents[1] / "code-gossip"
PROFILE = json.loads((ROOT / "data/sounds.json").read_text())["effects"]["wood-thrush"]
SETTINGS = PROFILE["melody"]
SPEC = PROFILE["events"]["edit"]["melody"]


def test_walk_stays_in_scale_varies_and_prefers_small_steps():
    rng = random.Random(42)
    notes = []
    for _ in range(2000):
        notes.extend(melody.compose(SETTINGS, SPEC, notes[-4:], rng))
    palette = melody.scale_notes(SETTINGS)
    assert set(notes) == set(palette)
    assert all(a != b for a, b in zip(notes, notes[1:]))
    steps = [abs(palette.index(a) - palette.index(b)) for a, b in zip(notes, notes[1:])]
    assert sum(step <= 2 for step in steps) / len(steps) > 0.8
    assert any(step > 2 for step in steps)
    # Recent history changes the transition weights, not just the random seed.
    assert melody.compose(SETTINGS, SPEC, [48], random.Random(2)) != melody.compose(
        SETTINGS, SPEC, [72], random.Random(2))


def test_event_phrases_keep_their_identity_and_envelopes():
    for event, data in PROFILE["events"].items():
        spec = data["melody"]
        for seed in range(30):
            notes = melody.compose(SETTINGS, spec, [60, 63], random.Random(seed))
            assert set(notes) <= set(melody.scale_notes(SETTINGS))
            melody.sox_args(notes, spec, 0.4)
            phrase = spec["phrase"]
            if phrase == "resolve":
                assert event in {"stop", "session_end"}
                assert (notes[-1] - SETTINGS["root"]) % 12 == 0
                assert (notes[0] - notes[1]) % 12 == 7
            elif phrase == "rise":
                assert notes[0] < notes[1]
            elif phrase == "fall":
                assert notes[0] > notes[1]
            elif phrase == "question":
                assert notes[0] == notes[1]
            else:
                assert len(notes) == 1
            if phrase != "resolve" and len(notes) == 2:
                assert not ((notes[0] - SETTINGS["root"]) % 12 == 7
                            and (notes[1] - SETTINGS["root"]) % 12 == 0)


def test_history_persists_and_previews_are_isolated(tmp_path):
    with patch.object(melody, "compose", wraps=melody.compose) as compose:
        first = melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)
        second = melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)
        assert compose.call_args.args[2] == first
        assert first != second
        melody.next_notes(SETTINGS, SPEC, "wood-thrush", preview=True, state_dir=tmp_path)
        assert compose.call_args.args[2] == []
        melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)
        assert compose.call_args.args[2] == first + second


def test_idle_and_corrupt_state_restart_cleanly(tmp_path):
    with patch.object(melody.time, "clock_gettime", return_value=1000):
        melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)
    with patch.object(melody.time, "clock_gettime", return_value=1000 + melody.IDLE_SECONDS), \
            patch.object(melody, "compose", wraps=melody.compose) as compose:
        melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)
        assert compose.call_args.args[2] == []
    for contents in ('{broken', '[]', '{"bad": {"time": "wrong", "notes": null}}'):
        (tmp_path / "state.json").write_text(contents)
        assert melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)


def test_state_failure_still_produces_sound(tmp_path):
    tmp_path.joinpath("blocked").write_text("not a directory")
    assert melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path / "blocked")
    with patch.object(melody, "acquire_lock", side_effect=TimeoutError):
        assert melody.next_notes(SETTINGS, SPEC, "wood-thrush", state_dir=tmp_path)


def _concurrent_note(args):
    directory, profile = args
    return melody.next_notes(SETTINGS, SPEC, profile, state_dir=directory)


def test_concurrent_hooks_preserve_each_profiles_history(tmp_path):
    with ProcessPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(_concurrent_note, [(tmp_path, str(i)) for i in range(12)]))
    state = json.loads((tmp_path / "state.json").read_text())
    assert len(state) == len(results) == 12
    assert all(len(record["notes"]) == 1 for record in state.values())


def test_each_note_receives_channel_volume():
    notes = [60, 63]
    args = melody.sox_args(notes, SPEC, 0.25)
    chains = " ".join(args).split(" : ")
    assert len(chains) == 2
    assert all(chain.endswith("vol 0.25") for chain in chains)
    assert "261.625565" in chains[0]
    assert "311.126984" in chains[1]
    assert all("synth 0.250000 sine" in chain for chain in chains)


def test_hook_uses_configured_python_and_persistent_history(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq is required for hook dispatch")
    runtime = tmp_path / "runtime"
    (runtime / "engine").mkdir(parents=True)
    (runtime / "configs").mkdir()
    (runtime / "data").mkdir()
    for name in ("play.sh", "melody.py", "playback_gate.py"):
        shutil.copy(ROOT / "engine" / name, runtime / "engine" / name)
    shutil.copy(ROOT / "paths.py", runtime / "paths.py")
    shutil.copy(ROOT / "data/sounds.json", runtime / "data/sounds.json")
    python = tmp_path / "configured-python"
    python.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    python.chmod(0o755)
    (runtime / "configs/config.json").write_text(json.dumps({
        "effects_on": True, "effects_profile": "wood-thrush", "effects_volume": 40,
        "voice_on": False, "python3_path": str(python), "sound_spacing_on": False,
    }))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    player = fake_bin / "play"
    player.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$AUDIO_LOG"\n')
    player.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("FORCE_")}
    env.update(PATH=str(fake_bin) + os.pathsep + env.get("PATH", ""), AUDIO_LOG=str(tmp_path / "audio.log"))
    for event in ("edit", "read"):
        result = subprocess.run(["bash", str(runtime / "engine/play.sh"), event],
                                input='{}', capture_output=True, text=True, env=env, timeout=10)
        assert result.returncode == 0, result.stderr
    state = json.loads((runtime / "state/melody/state.json").read_text())
    assert len(state) == 1
    notes = next(iter(state.values()))["notes"]
    assert len(notes) == 2 and notes[0] != notes[1]
    log = (tmp_path / "audio.log").read_text()
    assert log.count("synth\n") == 2
    assert log.count("vol\n0.4\n") == 2


def test_real_sox_renders_the_whole_phrase(tmp_path):
    sox = melody.executable("sox")
    if not sox:
        pytest.skip("SoX is optional")
    import wave
    spec = PROFILE["events"]["stop"]["melody"]
    target = tmp_path / "cue.wav"
    subprocess.run([sox, "-n", "-r", "24000", "-b", "16", str(target),
                    *melody.sox_args([67, 60], spec, 0.4)], check=True, capture_output=True)
    with wave.open(str(target)) as audio:
        assert audio.getnframes() / audio.getframerate() == pytest.approx(spec["duration"], abs=0.001)
