"""Keep the browser composer and its recording bank faithful to the local engine."""
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
from unittest.mock import patch

import pytest

from engine import melody
from scripts.preview_content import melody_catalog, melody_phrases, read

ROOT = Path(__file__).resolve().parents[1]
PROFILE = read("code-gossip/data/sounds.json")["effects"]["wood-thrush"]


class RandomTape(random.Random):
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


def browser_results(script, cases):
    node = shutil.which("node")
    assert node, "Node is required to verify the browser composer against Python"
    result = subprocess.run([node, "-e", """
const melody = require(process.argv[1]);
const cases = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
""" + script, str(ROOT / "docs/melody.js")], input=json.dumps(cases),
        text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_browser_composition_matches_python_for_every_event():
    rng = random.Random(8419)
    cases, expected = [], []
    palettes = [PROFILE["melody"],
                {"root":60, "scale":[0, 3, 5, 7, 10], "range":[48, 84]},
                {"root":50, "scale":[0, 2, 4, 5, 7, 9, 11], "range":[50, 74]},
                {"root":48, "scale":[0, 5, 7], "range":[48, 60]}]
    for settings in palettes:
        notes = melody.scale_notes(settings)
        for event_spec in PROFILE["events"].values():
            spec = event_spec["melody"]
            for index in range(40):
                history = rng.choices(notes + [None, "bad", -1, 64.5], k=rng.randrange(9))
                draws = [[0, 0], [.5, .5], [math.nextafter(1, 0)] * 2][index] if index < 3 else [rng.random(), rng.random()]
                cases.append(dict(settings=settings, spec=spec, history=history, draws=draws))
                expected.append(melody.compose(settings, spec, history, RandomTape(draws)))
    actual = browser_results("""
console.log(JSON.stringify(cases.map(({settings,spec,history,draws}) =>
 melody.compose(settings,spec,history,() => draws.shift()))));
""", cases)
    assert actual == expected


def test_browser_history_matches_runtime_expiry_and_profile_isolation(tmp_path):
    rng = random.Random(42)
    cases, expected = [], []
    for index, time in enumerate([1000, 1001, 1002, 1003, 1004, 1123, 1243, 1244, 1245, 1246, 1247, 1248]):
        settings = dict(PROFILE["melody"])
        if index == 9:
            settings["range"] = [48, 60]
        identity = ["effects", "other" if index in [3, 10] else "wood-thrush"]
        spec = PROFILE["events"][["edit", "session_start", "permission", "stop"][index % 4]]["melody"]
        draws = [rng.random(), rng.random()]
        cases.append(dict(settings=settings, spec=spec, identity=identity, time=time, draws=draws))
        with patch.object(melody.time, "clock_gettime", return_value=time):
            expected.append(melody.next_notes(settings, spec, identity, preview=True,
                state_dir=tmp_path, rng=RandomTape(draws)))
    actual = browser_results(f"""
let time, draws;
const history = melody.createHistory({{idleSeconds:{melody.IDLE_SECONDS}, now:()=>time, random:()=>draws.shift()}});
console.log(JSON.stringify(cases.map(item => {{
 time=item.time; draws=item.draws;
 return history.next(item.settings,item.spec,item.identity);
}})));
""", cases)
    assert actual == expected


def test_bank_covers_all_phrases_and_reserves_completion_cadence():
    settings = PROFILE["melody"]
    bank = melody_catalog()
    rng = random.Random(16)
    for event, event_spec in PROFILE["events"].items():
        spec = event_spec["melody"]
        phrases = melody_phrases(settings, spec)
        assert set(bank[f"effects/wood-thrush/{event}"]) == {",".join(map(str, notes)) for notes in phrases}
        history = []
        for _ in range(300):
            selected = melody.compose(settings, spec, history, rng)
            assert tuple(selected) in phrases
            history = (history + selected)[-4:]
        for notes in phrases:
            cadence = len(notes) == 2 and (notes[0] - settings["root"]) % 12 == 7 and (notes[1] - settings["root"]) % 12 == 0
            assert cadence == (event in {"stop", "session_end"})


@pytest.mark.parametrize("change", ["missing", "wrong-file"])
def test_missing_or_wrong_melody_recording_blocks_the_build(monkeypatch, change):
    import scripts.build_pages as pages
    original = pages.read
    def changed(path, root):
        value = original(path, root)
        if path.endswith("manifest.json"):
            bank = value["melodies"]["effects/wood-thrush/edit"]
            key = next(iter(bank))
            if change == "missing":
                del bank[key]
            else:
                bank[key] = "0" * 24 + ".mp3"
        return value
    monkeypatch.setattr(pages, "read", changed)
    with pytest.raises(ValueError, match="Melody recording coverage"):
        pages.verify_recordings()
