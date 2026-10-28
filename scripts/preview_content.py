"""Pure inputs/identities shared by preview recording, Pages builds, and tests."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code-gossip"))
from soundbar.catalog import KOKORO_VOICES, preview_catalog

MODEL = "hexgrad/Kokoro-82M"
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
VOICE_SAMPLE = "Ready when you are."
INPUTS = [
    "code-gossip/data/sounds.json", "code-gossip/configs/config.defaults.json",
    "code-gossip/configs/phrases.defaults.json", "code-gossip/configs/narrator_styles.defaults.json",
    "code-gossip/soundbar/catalog.py", "code-gossip/engine/melody.py",
    "code-gossip/data/sounds/generals/generate.sh", "docs/demo-commentary.json",
    "scripts/preview_content.py", "scripts/render_previews.py",
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
                for index in range(len(variants)):
                    yield layer, name, event, index

def sound_id(layer, profile, event, variant):
    return f"{layer}/{profile}/{event}/{variant}"
