"""Pure inputs/identities shared by preview recording, Pages builds, and tests."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code-gossip"))
from soundbar.catalog import KOKORO_VOICES, preview_catalog
from engine.melody import compose, IDLE_SECONDS

MODEL = "hexgrad/Kokoro-82M"
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
VOICE_SAMPLE = "Ready when you are."
INPUTS = [
    "code-gossip/data/sounds.json", "code-gossip/configs/config.defaults.json",
    "code-gossip/configs/phrases.defaults.json", "code-gossip/configs/narrator_styles.defaults.json",
    "code-gossip/soundbar/catalog.py", "code-gossip/engine/melody.py",
    "code-gossip/data/sounds/generals/generate.sh", "docs/demo-commentary.json",
    "scripts/preview_content.py", "scripts/render_previews.py", "docs/melody.js",
]

def read(path, root=ROOT):
    return json.loads((root / path).read_text())

def digest(value):
    return hashlib.sha256(value).hexdigest()

def identity(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())[:24]

def input_hashes(root=ROOT):
    paths = INPUTS + sorted(str(p.relative_to(root)) for p in (root / "code-gossip/data/sounds").rglob("*.mp3"))
    return {p: digest((root / p).read_bytes()) for p in paths}

def speech_key(voice, text):
    return identity([MODEL, REVISION, voice, text, 1, "mp3-128k-v1"])

def speech_requests(root=ROOT):
    phrases = read("code-gossip/configs/phrases.defaults.json", root)
    commentary = read("docs/demo-commentary.json", root)
    styles = read("code-gossip/configs/narrator_styles.defaults.json", root)
    if set(commentary["styles"]) != set(styles):
        raise ValueError("Record examples for every shipped narrator style")
    texts = {VOICE_SAMPLE}
    for variants in phrases.values():
        for variant in variants:
            texts.update(variant if isinstance(variant, list) else [variant])
    for examples in commentary["styles"].values():
        if len(examples) != len(commentary["events"]):
            raise ValueError("Each style needs every example-session event")
        texts.update(examples)
    return [(v["id"], text) for v in KOKORO_VOICES for text in sorted(texts)]

def sound_requests(root=ROOT):
    sounds = read("code-gossip/data/sounds.json", root)
    for layer, profiles in preview_catalog(sounds).items():
        for name, events in profiles.items():
            for event, variants in events.items():
                if "melody" in sounds[layer][name]["events"][event]:
                    continue
                for index in range(len(variants)):
                    yield layer, name, event, index

def sound_id(layer, profile, event, variant):
    return f"{layer}/{profile}/{event}/{variant}"


def melody_phrases(settings, spec):
    """Enumerate every branch of the real composer, without duplicating its rules.

    Empty history allows every starting pitch. History only changes weights or
    removes a repeated starting pitch, so it cannot introduce additional phrases.
    """
    class Branch(Exception):
        def __init__(self, candidates):
            self.candidates = candidates

    class Choices:
        def __init__(self, prefix):
            self.prefix = iter(prefix)

        def choices(self, candidates, weights, k):
            try:
                return [next(self.prefix)]
            except StopIteration:
                raise Branch(candidates)

    pending, phrases = [()], set()
    while pending:
        prefix = pending.pop()
        try:
            phrases.add(tuple(compose(settings, spec, rng=Choices(prefix))))
        except Branch as branch:
            pending.extend(prefix + (candidate,) for candidate in branch.candidates)
    return sorted(phrases)


def melody_requests(root=ROOT):
    source = digest((root / "code-gossip/engine/melody.py").read_bytes())
    sounds = read("code-gossip/data/sounds.json", root)
    for layer, profiles in sounds.items():
        for profile, data in profiles.items():
            for event, event_spec in data["events"].items():
                if "melody" not in event_spec:
                    continue
                spec = event_spec["melody"]
                for notes in melody_phrases(data["melody"], spec):
                    filename = identity([source, data["melody"], spec, notes, "mp3-128k-v1"]) + ".mp3"
                    yield f"{layer}/{profile}/{event}", notes, spec, filename


def melody_catalog(root=ROOT):
    result = {}
    for event, notes, _, filename in melody_requests(root):
        result.setdefault(event, {})[",".join(map(str, notes))] = filename
    return result
