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


def test_website_is_tested_with_package_then_deployed_without_rebuilding(workflow, repo_root):
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["test"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build matching website")
    assert build["env"]["PACKAGE_TAG"] == "${{ github.event_name == 'release' && github.event.release.tag_name || '1.2.3' }}"
    assert '--tag "$PACKAGE_TAG" --package dist/code-gossip.zip' in build["run"]
    tests = next(step for step in steps if step.get("name") == "Test installers, updates, and development mode")
    assert "node tests/test_pages.cjs" in tests["run"]
    upload = next(step for step in steps if step.get("with", {}).get("name") == "tested-website")
    assert steps.index(build) < steps.index(tests) < steps.index(upload)
    assert upload["with"]["include-hidden-files"] == "true"
    deploy_steps = pages["jobs"]["deploy"]["steps"]
    assert any(step.get("with", {}).get("name") == "tested-website" for step in deploy_steps)
    verification = next(step for step in deploy_steps if step.get("name") == "Verify the tested website and installer")
    assert verification["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    assert verification["env"]["RELEASE_COMMIT"] == "${{ github.sha }}"
    assert 'scripts/verify_pages.py' in verification["run"]
    assert not any('build_pages.py' in step.get('run', '') for step in deploy_steps)
    upload_pages = next(step for step in deploy_steps if step.get("name") == "Upload marketing page")
    assert upload_pages["with"]["path"] == "dist/pages"
    for name in ("Configure Pages", "Upload marketing page", "Deploy marketing page"):
        assert next(s for s in deploy_steps if s.get("name") == name)["if"] == "steps.latest.outputs.deploy == 'true'"


@pytest.mark.parametrize("assets,lookup_failure,upload_failure,published,uploads,success", [
    ("", "0", "0", "identical", True, True),
    ("other.zip", "0", "0", "identical", True, True),
    ("code-gossip.zip", "0", "0", "identical", False, True),
    ("code-gossip.zip", "0", "0", "different", False, False),
    ("", "1", "0", "identical", False, False),
    ("", "0", "1", "identical", True, False),
])
def test_publish_step(workflow, tmp_path, assets, lookup_failure, upload_failure, published, uploads, success):
    gh = tmp_path / "gh"
    gh.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$GH_CALLS"
case "$1 $2" in
  "release view")
    test "$LOOKUP_FAILURE" = 0 || exit 1
    printf '%s\\n' "$EXISTING_ASSETS" ;;
  "release upload") test "$UPLOAD_FAILURE" = 0 ;;
  "release download") printf '%s' "$PUBLISHED" > "$RUNNER_TEMP/published-package/code-gossip.zip" ;;
  *) exit 99 ;;
esac
''')
    gh.chmod(0o755)
    calls = tmp_path / "calls"
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/code-gossip.zip").write_text("identical")
    step = workflow["jobs"]["publish"]["steps"][-1]
    assert step["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    result = subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=tmp_path, env={
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "GH_CALLS": str(calls), "RELEASE_TAG": "0.9.2", "EXISTING_ASSETS": assets,
        "LOOKUP_FAILURE": lookup_failure, "UPLOAD_FAILURE": upload_failure,
        "RUNNER_TEMP": str(tmp_path), "PUBLISHED": published,
    }, capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr
    commands = calls.read_text().splitlines()
    assert commands[0].startswith("release view 0.9.2 --json assets --jq ")
    assert [c for c in commands if c.startswith("release upload")] == (["release upload 0.9.2 dist/code-gossip.zip"] if uploads else [])
    assert all(c.startswith(("release view", "release upload", "release download")) for c in commands)


@pytest.mark.parametrize("latest,deploy", [("1.2.3", True), ("1.2.4", False)])
def test_older_release_cannot_overwrite_latest_page(repo_root, tmp_path, latest, deploy):
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in pages["jobs"]["deploy"]["steps"] if s.get("id") == "latest")
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$LATEST"\n')
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], check=True, env={
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "LATEST": latest, "RELEASE_TAG": "1.2.3", "GITHUB_OUTPUT": str(output),
    })
    assert ("deploy=true" in output.read_text()) == deploy
