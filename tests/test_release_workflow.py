"""Exercise the actual publication step without writing to GitHub."""

import os
import shutil
import subprocess

import pytest
import yaml


@pytest.fixture
def workflow(repo_root):
    return yaml.load((repo_root / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)


def test_only_release_publication_triggers_upload_and_deployment(workflow, repo_root):
    assert workflow["on"] == {
        "pull_request": "",
        "release": {"types": ["published"]},
    }
    assert workflow["jobs"]["publish"]["if"] == "github.event_name == 'release'"
    assert workflow["jobs"]["pages"]["needs"] == "publish"
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    assert pages["on"] == {"workflow_call": ""}


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2.3"])
def test_website_version_comes_from_published_release(repo_root, tmp_path, tag):
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    step = next(step for step in pages["jobs"]["deploy"]["steps"] if step.get("name") == "Display the released version")
    assert step["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    (tmp_path / "docs").mkdir()
    page = tmp_path / "docs/index.html"
    shutil.copy2(repo_root / "docs/index.html", page)
    subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=tmp_path,
                   env={**os.environ, "RELEASE_TAG": tag}, check=True)
    assert f"Latest release · {tag}" in page.read_text()
    assert "<!-- RELEASE_VERSION -->" not in page.read_text()


@pytest.mark.parametrize("assets,lookup_failure,upload_failure,uploads,success", [
    ("", "0", "0", True, True),                 # Published release, no package yet.
    ("other.zip", "0", "0", True, True),        # Preserve unrelated release assets.
    ("code-gossip.zip", "0", "0", False, True),  # Rerun after a successful upload.
    ("", "1", "0", False, False),              # Failed lookup must not create a release.
    ("", "0", "1", True, False),               # Upload failure must stop deployment.
])
def test_publish_step(workflow, tmp_path, assets, lookup_failure, upload_failure, uploads, success):
    gh = tmp_path / "gh"
    gh.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$GH_CALLS"
case "$1 $2" in
  "release view")
    test "$LOOKUP_FAILURE" = 0 || exit 1
    printf '%s\\n' "$EXISTING_ASSETS" ;;
  "release upload") test "$UPLOAD_FAILURE" = 0 ;;
  *) exit 99 ;;
esac
''')
    gh.chmod(0o755)
    calls = tmp_path / "calls"
    step = workflow["jobs"]["publish"]["steps"][-1]
    assert step["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    result = subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], env={
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "GH_CALLS": str(calls), "RELEASE_TAG": "0.9.2", "EXISTING_ASSETS": assets,
        "LOOKUP_FAILURE": lookup_failure, "UPLOAD_FAILURE": upload_failure,
    }, capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr
    commands = calls.read_text().splitlines()
    assert commands[0].startswith("release view 0.9.2 --json assets --jq ")
    assert commands[1:] == (["release upload 0.9.2 dist/code-gossip.zip"] if uploads else [])
