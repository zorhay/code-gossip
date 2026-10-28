#!/usr/bin/env python3
"""Build Pages from the current Soundbar and verified, prerecorded shipped content."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

try:
    from .preview_content import ROOT, digest, input_hashes, read, speech_requests, speech_key, sound_requests, sound_id, VOICE_SAMPLE, melody_catalog, IDLE_SECONDS
except ImportError:
    from preview_content import ROOT, digest, input_hashes, read, speech_requests, speech_key, sound_requests, sound_id, VOICE_SAMPLE, melody_catalog, IDLE_SECONDS
from soundbar.catalog import EVENTS, DIALOGUE_EVENTS, KOKORO_VOICES, NARRATOR_PROVIDERS, TTS_ENGINES, preview_catalog

RUNTIME_INPUTS = ["soundbar/ui.html", "soundbar/ui.js", "soundbar/catalog.py", "engine/melody.py",
                  "configs/config.defaults.json", "configs/phrases.defaults.json",
                  "configs/narrator_styles.defaults.json", "data/sounds.json"]

def runtime_inputs(root=ROOT):
    recorded = (name.removeprefix("code-gossip/") for name in input_hashes(root)
                if name.startswith("code-gossip/"))
    return sorted(set(RUNTIME_INPUTS) | set(recorded))

def verify_recordings(root=ROOT):
    manifest = read("docs/preview-audio/manifest.json", root)
    if manifest["inputs"] != input_hashes(root):
        raise ValueError("Preview inputs changed. Run scripts/render_previews.py with the Kokoro Python before publishing.")
    expected_speech = {speech_key(v, text) for v, text in speech_requests(root)}
    expected_sounds = {sound_id(*request) for request in sound_requests(root)}
    if set(manifest["speech"]) != expected_speech or set(manifest["sounds"]) != expected_sounds:
        raise ValueError("Preview coverage does not match all shipped voices, phrases, styles, and sound variants")
    if manifest.get("melodies") != melody_catalog(root):
        raise ValueError("Melody recording coverage differs from the runtime composer")
    files = set(manifest["speech"].values()) | set(manifest["sounds"].values()) | {
        name for bank in manifest["melodies"].values() for name in bank.values()}
    if files != set(manifest["files"]):
        raise ValueError("Unverified preview files")
    for name, expected in manifest["files"].items():
        if not re.fullmatch(r"[a-f0-9]{24}\.mp3", name) or digest((root / "docs/preview-audio" / name).read_bytes()) != expected:
            raise ValueError(f"Missing or changed preview: {name}")
    return manifest

def verify_package(package, tag, root=ROOT):
    from updates.entities import Version
    version = str(Version.parse(tag))
    with zipfile.ZipFile(package) as bundle:
        if bundle.read("release/code-gossip/VERSION").decode().strip() != version:
            raise ValueError("Pages version differs from installation package")
        for path in runtime_inputs(root):
            if bundle.read("release/code-gossip/" + path) != (root / "code-gossip" / path).read_bytes():
                raise ValueError(f"Pages source differs from installation package: {path}")
    return version

def build(output, *, tag="development", package=None, root=ROOT):
    recordings = verify_recordings(root)
    if tag != "development" and package is None:
        raise ValueError("Release Pages builds require the matching installation package")
    version = verify_package(package, tag, root) if package else "development"
    source = (root / "code-gossip/soundbar/ui.html").read_text()
    head = re.search(r"<head>(.*?)</head>", source, re.S)[1]
    head = re.sub(r"<title>.*?</title>|<meta[^>]*>", "", head)
    body = re.search(r"<body>(.*?)</body>", source, re.S)[1]
    body = body.replace('<script src="/ui.js"></script>', '')
    template = (root / "docs/index.html").read_text()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    build_commit = commit + ("-dirty" if status else "")
    release_url = "https://github.com/zorhay/code-gossip/releases/" + ("latest" if tag == "development" else "tag/" + tag)
    for key, value in {"SOUNDBAR_HEAD":head, "SOUNDBAR_BODY":body, "RELEASE_URL":html.escape(release_url), "RELEASE_VERSION":html.escape(tag), "BUILD_COMMIT":html.escape(commit[:12] + ("-dirty" if status else ""))}.items():
        template = template.replace("<!-- " + key + " -->", value)
    template = template.replace("<!-- INSTALL_RELEASE -->", "" if tag == "development" else "--release " + html.escape(tag) + " ")
    sounds = read("code-gossip/data/sounds.json", root)
    defaults = read("code-gossip/configs/config.defaults.json", root)
    phrases = read("code-gossip/configs/phrases.defaults.json", root)
    styles = read("code-gossip/configs/narrator_styles.defaults.json", root)
    setup = {"effects":{p:{"ready":True,"missing":[],"message":"Prerecorded"} for p in sounds["effects"]},
             "clips":{p:{"ready":True,"message":"Prerecorded"} for p in sounds["voice"]}, "kokoro":True,"say":False}
    data = {"status":{**defaults,"setup":setup,"effects_profiles":sounds["effects"],
            "preview_catalog":preview_catalog(sounds), "phrases":phrases,"phrases_defaults":phrases,
            "events":EVENTS,"dialogue_events":sorted(DIALOGUE_EVENTS),"voices":[],
            "kokoro_voices":KOKORO_VOICES,"tts_engines":TTS_ENGINES,"narrator_providers":NARRATOR_PROVIDERS,
            "narrator_styles":styles,"narrator_styles_defaults":styles},
            "sounds":recordings["sounds"], "melodies":recordings["melodies"], "melodyIdleSeconds":IDLE_SECONDS,
            "speech":{}, "voiceSample":VOICE_SAMPLE,
            "commentary":read("docs/demo-commentary.json", root)}
    for voice, text in speech_requests(root):
        data["speech"].setdefault(voice, {})[text] = recordings["speech"][speech_key(voice, text)]
    if output.resolve() in (root.resolve(), (root / "docs").resolve()):
        raise ValueError("Output must be a separate build directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "index.html").write_text(template)
    (output / "demo-data.json").write_text(json.dumps(data, ensure_ascii=False) + "\n")
    (output / ".nojekyll").touch()
    shutil.copy2(root / "code-gossip/soundbar/ui.js", output / "ui.js")
    for name in ("player.css", "melody.js", "demo.js", "install.sh", "credits.html"):
        shutil.copy2(root / "docs" / name, output / name)
    audio = output / "preview-audio"
    audio.mkdir()
    for name in recordings["files"]:
        shutil.copy2(root / "docs/preview-audio" / name, audio / name)
    metadata = {"version":version,"tag":tag,"commit":build_commit,
                "runtime":{p:digest((root / "code-gossip" / p).read_bytes()) for p in runtime_inputs(root)},
                "previewInputs":recordings["inputs"], "packageSha256":digest(Path(package).read_bytes()) if package else None}
    metadata["files"] = {str(p.relative_to(output)):digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="development")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/pages")
    args = parser.parse_args()
    result = build(args.output, tag=args.tag, package=args.package)
    print(f"Pages {result['tag']} · {result['commit']} → {args.output}")

if __name__ == "__main__":
    main()
