"""Release/source parity and complete, untampered prerecorded demo coverage."""
import json
import re
import shutil
import zipfile

import pytest

from scripts.build_pages import build, verify_package, verify_recordings, RUNTIME_INPUTS
from scripts.preview_content import read
from scripts.verify_pages import verify
from scripts.package_release import build_package


@pytest.fixture(scope="module")
def website(tmp_path_factory):
    directory = tmp_path_factory.mktemp("website")
    from scripts.preview_content import ROOT
    package = build_package(ROOT, "1.2.3", directory / "code-gossip.zip")
    site = directory / "pages"
    metadata = build(site, tag="1.2.3", package=package)
    return site, package, metadata


def test_shipped_catalog_and_ui_match_installer(website, repo_root):
    site, package, metadata = website
    data = json.loads((site / "demo-data.json").read_text())
    for name, key in [("phrases", "phrases"), ("narrator_styles", "narrator_styles")]:
        assert data["status"][key] == read(f"code-gossip/configs/{name}.defaults.json")
    defaults = read("code-gossip/configs/config.defaults.json")
    assert {k: data["status"][k] for k in defaults} == defaults
    assert data["status"]["effects_profiles"] == read("code-gossip/data/sounds.json")["effects"]
    assert (site / "ui.js").read_bytes() == (repo_root / "code-gossip/soundbar/ui.js").read_bytes()
    local = (repo_root / "code-gossip/soundbar/ui.html").read_text()
    body = re.search(r"<body>(.*?)</body>", local, re.S)[1].replace('<script src="/ui.js"></script>', '')
    assert body in (site / "index.html").read_text(), "The actual app markup must be embedded, not a stale copy"
    assert re.search(r"<style>.*?</style>", local, re.S)[0] in (site / "index.html").read_text()
    assert '<video' not in (site / "index.html").read_text()
    assert 'src="/ui.js"' not in (site / "index.html").read_text()
    assert "Release 1.2.3" in (site / "index.html").read_text()
    assert "releases/tag/1.2.3" in (site / "index.html").read_text()
    assert "bash -s -- --release 1.2.3 --all" in (site / "index.html").read_text()
    assert "data/sounds/paper/pencil.mp3" in metadata["runtime"]
    assert verify(site, package, "1.2.3", metadata["commit"]) == metadata


@pytest.mark.parametrize("relative", [
    "code-gossip/data/sounds.json", "code-gossip/configs/phrases.defaults.json",
    "code-gossip/configs/config.defaults.json", "code-gossip/configs/narrator_styles.defaults.json",
    "code-gossip/soundbar/catalog.py", "docs/demo-commentary.json",
])
def test_changed_content_requires_new_recordings(repo_root, tmp_path, relative):
    # A sparse copy exercises the actual filesystem hash gate without touching settings.
    for name in read("docs/preview-audio/manifest.json")["inputs"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / name, target)
    audio = tmp_path / "docs/preview-audio"
    audio.mkdir()
    shutil.copy2(repo_root / "docs/preview-audio/manifest.json", audio)
    from scripts.preview_content import input_hashes
    assert input_hashes(tmp_path) == read("docs/preview-audio/manifest.json")["inputs"]
    path = tmp_path / relative
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="Preview inputs changed"):
        verify_recordings(tmp_path)


def test_all_preview_files_have_matching_content_and_coverage(repo_root):
    manifest = verify_recordings()
    assert len(manifest["speech"]) > 1000
    assert len(manifest["sounds"]) > 100
    assert set(manifest["files"]) == {p.name for p in (repo_root / "docs/preview-audio").glob("*.mp3")}


def test_missing_audio_aborts_build_before_replacing_output(repo_root, tmp_path, monkeypatch):
    import scripts.build_pages as pages
    original = pages.read
    def missing(path, root):
        value = original(path, root)
        if path.endswith("manifest.json"):
            value["speech"].pop(next(iter(value["speech"])))
        return value
    monkeypatch.setattr(pages, "read", missing)
    output = tmp_path / "pages"
    output.mkdir()
    sentinel = output / "old-build"
    sentinel.write_text("preserve")
    with pytest.raises(ValueError, match="coverage"):
        pages.build(output)
    assert sentinel.read_text() == "preserve"


@pytest.mark.parametrize("relative", RUNTIME_INPUTS + ["data/sounds/paper/pencil.mp3", "data/sounds/generals/generate.sh"])
def test_release_rejects_different_installer_sources(website, tmp_path, relative):
    _, package, _ = website
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(package) as source, zipfile.ZipFile(changed, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "release/code-gossip/" + relative:
                content += b"\nchanged"
            target.writestr(info, content)
    with pytest.raises(ValueError, match="differs from installation package"):
        verify_package(changed, "1.2.3")


def test_release_tag_commit_package_and_files_are_checked(website, tmp_path):
    site, package, metadata = website
    with pytest.raises(ValueError, match="commit/tag"):
        verify(site, package, "1.2.4", metadata["commit"])
    with pytest.raises(ValueError, match="commit/tag"):
        verify(site, package, "1.2.3", "wrong-commit")
    with pytest.raises(ValueError, match="versions differ|version differs"):
        verify_package(package, "1.2.4")
    changed = tmp_path / "changed.zip"
    changed.write_bytes(package.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="installation package"):
        verify(site, changed, "1.2.3", metadata["commit"])
    original = (site / "demo.js").read_bytes()
    try:
        (site / "demo.js").write_bytes(original + b"\nchanged")
        with pytest.raises(ValueError, match="changed after testing"):
            verify(site, package, "1.2.3", metadata["commit"])
    finally:
        (site / "demo.js").write_bytes(original)


def test_release_build_requires_package(tmp_path):
    with pytest.raises(ValueError, match="require the matching"):
        build(tmp_path / "pages", tag="1.2.3")
