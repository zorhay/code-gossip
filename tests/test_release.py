"""Build real packages, then exercise installation from archives and checkouts."""

import io
import json
import subprocess
import zipfile

import pytest
from scripts.package_release import build_package
from updates import github, source
from updates.constants import REQUIRED_SOURCE_FILES
from updates.entities import Release, Version
from updates.errors import UpdateError
from updates.storage import installed_version
from tests.test_installer import sandbox


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2.3"])
def test_package_generates_version_and_excludes_local_files(tmp_path, tag):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    for name in REQUIRED_SOURCE_FILES:
        if name == "code-gossip/VERSION":
            continue
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tracked source")
    (checkout / "install.sh").chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=checkout, check=True)
    (checkout / "code-gossip/configs/config.json").write_text('{"secret":"local"}')
    archive = build_package(checkout, tag, tmp_path / "code-gossip.zip")
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read("release/code-gossip/VERSION") == b"1.2.3\n"
        assert "release/code-gossip/configs/config.json" not in bundle.namelist()
        assert bundle.getinfo("release/install.sh").external_attr >> 16 & 0o111
    assert not (checkout / "code-gossip/VERSION").exists()


def test_normal_checkout_and_package_install_the_same_release(sandbox, repo_root, release_package, tmp_path):
    home, env, run = sandbox
    assert not (repo_root / "code-gossip/VERSION").exists()
    run("install.sh", "--agents", "codex")
    root = home / ".code-gossip"
    assert installed_version(root) == "1.2.3"
    before = (root / "installer.py").read_bytes()
    run(root / "uninstall.sh", "--all", "--purge")
    unpacked = source.extract_archive(release_package, tmp_path / "unpacked")
    # A downloaded package installs entirely offline.
    env.pop("TEST_RELEASE_DIRECTORY")
    run(unpacked / "install.sh", "--agents", "codex")
    assert installed_version(root) == "1.2.3"
    assert (root / "installer.py").read_bytes() == before
    run(root / "uninstall.sh", "--all", "--purge")


def test_missing_package_aborts_without_installing(sandbox, release_directory):
    home, _, run = sandbox
    metadata = json.loads((release_directory / "release.json").read_text())
    metadata["assets"] = []
    (release_directory / "release.json").write_text(json.dumps(metadata))
    result = run("install.sh", "--agents", "codex", success=False)
    assert "installable code-gossip.zip" in result.stderr
    assert not (home / ".code-gossip").exists()
    assert not (home / ".codex").exists()


def test_package_version_must_match_release(tmp_path, release_package):
    unpacked = source.extract_archive(release_package, tmp_path / "source")
    with pytest.raises(UpdateError, match="does not match"):
        source.validate_source(unpacked, Release(Version.parse("9.9.9"), "9.9.9", 99, ""))


def test_asset_discovery_pins_download_to_uploaded_asset(monkeypatch, tmp_path):
    metadata = {"tag_name": "v1.2.3", "id": 9, "assets": [
        {"name": "other.zip", "id": 90, "state": "uploaded"},
        {"name": "code-gossip.zip", "id": 91, "state": "uploaded"},
    ]}
    requests = []
    def request(url, timeout, **kwargs):
        requests.append((url, kwargs))
        return io.BytesIO(json.dumps(metadata).encode() if url.endswith("/latest") else b"package")
    monkeypatch.setattr(github, "request", request)
    release = github.latest_release()
    assert release.asset_id == 91 and str(release.version) == "1.2.3"
    assert github.download_release(release, tmp_path).read_bytes() == b"package"
    assert requests[-1][0].endswith("/releases/assets/91")
    assert requests[-1][1] == {"accept": "application/octet-stream"}


@pytest.mark.parametrize("assets", [[], [{"name": "code-gossip.zip", "id": 91, "state": "new"}]])
def test_incomplete_releases_are_not_offered(monkeypatch, assets):
    monkeypatch.setattr(github, "request", lambda *a: io.BytesIO(json.dumps(
        {"tag_name": "1.2.3", "id": 9, "assets": assets}).encode()))
    with pytest.raises(UpdateError, match="installable"):
        github.latest_release()
