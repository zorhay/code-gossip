"""Exercise the actual publication step without writing to GitHub."""

import os
import shutil
import subprocess

import pytest
import yaml


@pytest.fixture
def workflow(repo_root):
    return yaml.load((repo_root / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)


def test_only_version_tag_pushes_trigger_publication(workflow, repo_root):
    assert workflow["on"] == {
        "pull_request": "",
        "push": {"tags": ["[0-9]*", "v[0-9]*"]},
    }
    assert workflow["jobs"]["publish"]["if"] == "github.event_name == 'push' && github.ref_type == 'tag'"
    assert workflow["jobs"]["pages"]["needs"] == ["publish", "validate"]
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(pages["on"]["workflow_call"]["inputs"]) == {"release_tag", "release_commit"}


def test_website_is_tested_with_package_then_deployed_without_rebuilding(workflow, repo_root):
    pages = yaml.load((repo_root / ".github/workflows/pages.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["build"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build matching website")
    assert build["env"]["PACKAGE_TAG"] == "${{ needs.validate.outputs.tag }}"
    assert '--tag "$PACKAGE_TAG" --package dist/code-gossip.zip' in build["run"]
    upload = next(step for step in steps if step.get("with", {}).get("name") == "website-candidate")
    assert steps.index(build) < steps.index(upload)
    assert upload["with"]["include-hidden-files"] == "true"
    browser = workflow["jobs"]["browser"]
    assert browser["needs"] == ["build", "validate"]
    assert browser["strategy"]["fail-fast"] == "false"
    suites = {suite["suite"]: suite for suite in browser["strategy"]["matrix"]["include"]}
    assert {name: suite["command"] for name, suite in suites.items()} == {
        "soundbar": "node tests/test_soundbar_ui.cjs",
        "pages": "node tests/test_pages.cjs",
        "installation": 'E2E_RELEASE_PACKAGE="$PWD/dist/code-gossip.zip" node tests/test_soundbar_e2e.cjs',
    }
    assert browser["steps"][-1]["run"] == "${{ matrix.command }}"
    downloads = {step.get("with", {}).get("name"): step for step in browser["steps"] if "download-artifact@" in step.get("uses", "")}
    assert downloads["website-candidate"]["with"]["path"] == "dist/pages"
    assert downloads["website-candidate"]["if"] == "matrix.suite == 'pages'"
    assert downloads["installation-package"]["with"]["path"] == "dist"
    assert downloads["installation-package"]["if"] == "matrix.suite != 'soundbar'"
    assert not any('build_pages.py' in step.get('run', '') or 'package_release.py' in step.get('run', '') for step in browser["steps"])
    deploy_steps = pages["jobs"]["deploy"]["steps"]
    assert any(step.get("with", {}).get("name") == "website-candidate" for step in deploy_steps)
    verification = next(step for step in deploy_steps if step.get("name") == "Verify the tested website and installer")
    assert verification["env"]["RELEASE_TAG"] == "${{ inputs.release_tag }}"
    assert verification["env"]["RELEASE_COMMIT"] == "${{ inputs.release_commit }}"
    assert 'scripts/verify_pages.py' in verification["run"]
    assert not any('build_pages.py' in step.get('run', '') for step in deploy_steps)
    upload_pages = next(step for step in deploy_steps if step.get("name") == "Upload website to Pages")
    assert upload_pages["with"]["path"] == "dist/pages"
    for name in ("Configure Pages", "Upload website to Pages", "Deploy website"):
        assert next(s for s in deploy_steps if s.get("name") == name)["if"] == "steps.latest.outputs.deploy == 'true'"


@pytest.mark.parametrize("failed_job,result", [(None, "success")] + [
    (job, result) for job in ("build", "runtime", "browser")
    for result in ("failure", "cancelled", "skipped")
])
def test_parallel_checks_gate_publication(workflow, failed_job, result):
    jobs = workflow["jobs"]
    gate = jobs["test"]
    assert gate["if"] == "always()", "A skipped suite must not hide a failed check"
    assert set(gate["needs"]) == {"build", "runtime", "browser"}
    assert jobs["publish"]["needs"] == ["test", "validate"]
    assert jobs["runtime"]["needs"] == jobs["build"]["needs"] == "validate"
    step = gate["steps"][0]
    expected = {"BUILD_RESULT": "build", "PYTHON_RESULT": "runtime", "BROWSER_RESULT": "browser"}
    assert step["env"] == {key: "${{ needs." + job + ".result }}" for key, job in expected.items()}
    env = {**os.environ, **{key: result if job == failed_job else "success" for key, job in expected.items()}}
    completed = subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], env=env)
    assert (completed.returncode == 0) == (failed_job is None)


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
