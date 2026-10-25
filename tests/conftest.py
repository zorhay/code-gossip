"""Common fixtures for soundbar integration tests."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from scripts.package_release import build_package

# Repo layout
REPO_ROOT = Path(__file__).resolve().parent.parent
SOUNDBAR_DIR = REPO_ROOT / "code-gossip"

# Direct script imports remain useful in unit tests; subprocess tests use entrypoints.
for directory in (SOUNDBAR_DIR, SOUNDBAR_DIR / "engine", SOUNDBAR_DIR / "hooks", SOUNDBAR_DIR / "soundbar"):
    sys.path.insert(0, str(directory))


@pytest.fixture(autouse=True)
def offline_release_checks(monkeypatch):
    """Automatic checks in child servers must never contact GitHub in tests."""
    support = str(REPO_ROOT / "tests/support")
    monkeypatch.setenv("PYTHONPATH", support + os.pathsep + os.environ.get("PYTHONPATH", ""))


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def release_package(tmp_path_factory):
    return build_package(REPO_ROOT, "1.2.3", tmp_path_factory.mktemp("package") / "code-gossip.zip")


@pytest.fixture
def release_directory(tmp_path, release_package):
    directory = tmp_path / "published-release"
    directory.mkdir()
    shutil.copy2(release_package, directory / "release.zip")
    (directory / "release.json").write_text(json.dumps({
        "tag_name": "1.2.3", "id": 9, "draft": False, "prerelease": False,
        "assets": [{"name": "code-gossip.zip", "id": 91, "state": "uploaded"}],
    }))
    return directory


@pytest.fixture
def soundbar_dir():
    return SOUNDBAR_DIR


@pytest.fixture
def sounds_json():
    return json.loads((SOUNDBAR_DIR / "data/sounds.json").read_text())


@pytest.fixture
def config_defaults():
    return json.loads((SOUNDBAR_DIR / "configs/config.defaults.json").read_text())


@pytest.fixture
def claude_hooks_json():
    return (SOUNDBAR_DIR / "hooks/claude-hooks.json").read_text()


@pytest.fixture
def play_script():
    return (SOUNDBAR_DIR / "engine/play.sh").read_text()


@pytest.fixture
def switch_script():
    return (SOUNDBAR_DIR / "switch.sh").read_text()
