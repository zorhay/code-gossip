"""Exercise the publication check against complete and mismatched archives."""

import subprocess
import sys
import zipfile

import pytest
from updates.constants import REQUIRED_SOURCE_FILES


@pytest.mark.parametrize("tag,version,success", [
    ("0.9.0", "0.8.0", False),  # The published archive that caused the failure.
    ("0.9.1", "0.9.1", True),
    ("v0.9.1", "0.9.1", True),
])
def test_release_check_uses_archive_version(tmp_path, repo_root, tag, version, success):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in REQUIRED_SOURCE_FILES:
            bundle.writestr("release/" + name, version + "\n" if name == "code-gossip/VERSION" else "fixture")
    original = archive.read_bytes()
    result = subprocess.run([sys.executable, "-B", str(repo_root / "scripts/check_release.py"),
                             tag, "--archive", str(archive)], capture_output=True, text=True)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    if not success:
        assert "Release version does not match" in result.stderr
    assert archive.read_bytes() == original
