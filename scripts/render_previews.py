#!/usr/bin/env python3
"""Record all shipped previews on macOS. Uses only defaults, never saved settings.

Run with the Kokoro Python: code-gossip/state/.venv/bin/python scripts/render_previews.py
Requires FFmpeg, SoX, and the voices used by Generals. Output is content-addressed;
rerunning reuses recordings and removes unreferenced files only after success.
"""
import argparse
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import tempfile

from preview_content import (ROOT, MODEL, REVISION, digest, identity, input_hashes,
                             read, sound_id, sound_requests, speech_key, speech_requests)
from engine.melody import compose, sox_args

OUT = ROOT / "docs/preview-audio"

def run(args):
    subprocess.run([str(a) for a in args], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE)

def encode(source, target):
    temporary = target.with_suffix(".tmp.mp3")
    run(["ffmpeg", "-v", "error", "-y", "-i", source, "-map_metadata", "-1",
         "-codec:a", "libmp3lame", "-b:a", "128k", temporary])
    temporary.replace(target)

def record_sounds(directory):
    manifest = read("code-gossip/data/sounds.json")
    result = {}
    # Generate the exact shipped clip lines in a disposable copy, never the install.
    generals = directory / "generals"
    generals.mkdir()
    shutil.copy2(ROOT / "code-gossip/data/sounds/generals/generate.sh", generals)
    run(["bash", generals / "generate.sh"])
    for layer, profile, event, variant in sound_requests():
        data = manifest[layer][profile]
        spec = data["events"][event]
        files = spec.get("sequence", [])[variant] if "sequence" in spec else [spec["files"][variant]] if "files" in spec else [spec["file"]] if "file" in spec else []
        sources = [Path(f) if f.startswith("/") else (generals if profile == "generals" else ROOT / "code-gossip/data" / data.get("dir", "")) / f for f in files]
        key = identity([spec, variant, data.get("melody"), [digest(p.read_bytes()) for p in sources], "mp3-128k-v1"])
        target = OUT / (key + ".mp3")
        if not target.exists():
            wav = directory / "effect.wav"
            if sources:
                # Decode separately, concatenate sequence members with the runtime gap.
                import numpy as np
                chunks = []
                for i, source in enumerate(sources):
                    if i:
                        chunks.append(np.zeros((round(spec.get("gap", .15) * 44100), 2), dtype="float32"))
                    pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(source), "-f", "f32le", "-ar", "44100", "-ac", "2", "-"])
                    chunks.append(np.frombuffer(pcm, dtype="float32").reshape(-1, 2))
                import soundfile as sf
                sf.write(wav, np.concatenate(chunks), 44100)
            else:
                args = shlex.split(spec["sox"]) if "sox" in spec else sox_args(compose(data["melody"], spec["melody"], rng=random.Random(0)), spec["melody"], 1)
                run(["sox", "-n", "-r", "44100", wav, *args])
            encode(wav, target)
        result[sound_id(layer, profile, event, variant)] = target.name
    return result

def record_speech(directory):
    import numpy as np
    import soundfile as sf
    import torch
    from huggingface_hub import snapshot_download
    from kokoro import KModel, KPipeline
    torch.set_num_threads(4)
    snapshot = Path(snapshot_download(MODEL, revision=REVISION,
                    allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/*.pt"]))
    model = KModel(repo_id=MODEL, config=str(snapshot / "config.json"),
                   model=str(snapshot / "kokoro-v1_0.pth")).eval()
    pipelines = {}
    result = {}
    requests = speech_requests()
    for i, (voice, text) in enumerate(requests):
        key = speech_key(voice, text)
        target = OUT / (key + ".mp3")
        if not target.exists():
            lang = voice[0]
            if lang not in pipelines:
                pipelines[lang] = KPipeline(lang_code=lang, repo_id=MODEL, model=model)
            chunks = [a.numpy() for _, _, a in pipelines[lang](text, voice=str(snapshot / "voices" / (voice + ".pt")), speed=1) if a is not None]
            if not chunks or not np.any(np.concatenate(chunks)):
                raise RuntimeError(f"No speech: {voice}: {text}")
            wav = directory / "speech.wav"
            sf.write(wav, np.concatenate(chunks), 24000)
            encode(wav, target)
        result[key] = target.name
        if i % 25 == 0 or i == len(requests) - 1:
            print(f"Kokoro {i + 1}/{len(requests)} · {voice}", flush=True)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech-only", action="store_true", help="Resume speech; reuse the last sound catalog")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="code-gossip-previews-") as temp:
        directory = Path(temp)
        sounds = read("docs/preview-audio/sounds.json") if args.speech_only else record_sounds(directory)
        (OUT / "sounds.json").write_text(json.dumps(sounds, indent=2) + "\n")
        speech = record_speech(directory)
    files = set(sounds.values()) | set(speech.values())
    manifest = {"inputs": input_hashes(), "model": MODEL, "revision": REVISION,
                "sounds": sounds, "speech": speech,
                "files": {name: digest((OUT / name).read_bytes()) for name in sorted(files)}}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in OUT.glob("*.mp3"):
        if path.name not in files:
            path.unlink()
    (OUT / "sounds.json").unlink(missing_ok=True)
    print(f"Recorded {len(files)} files in {OUT}")

if __name__ == "__main__":
    main()
