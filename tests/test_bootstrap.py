"""Run the piped bootstrap against real packages in disposable homes."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_installer import document, sandbox, snapshot


@pytest.fixture
def bootstrap(sandbox, repo_root, release_package, tmp_path):
    home, env, _ = sandbox
    binaries = Path(env["PATH"])
    for name in ("uname", "mktemp", "rm", "unzip"):
        (binaries / name).symlink_to(shutil.which(name))
    curl = binaries / "curl"
    curl.write_text('''#!/bin/bash
test "${TEST_DOWNLOAD_FAIL:-0}" = 0 || exit 22
test "$6" = https://github.com/zorhay/code-gossip/releases/latest/download/code-gossip.zip || exit 99
/bin/cp "$TEST_PACKAGE" "${!#}"
''')
    curl.chmod(0o755)
    temporary = tmp_path / "downloads with spaces"
    temporary.mkdir()
    env.update(TMPDIR=str(temporary), TEST_PACKAGE=str(release_package))
    # The downloaded package must install without fetching another release.
    env.pop("TEST_RELEASE_DIRECTORY")

    def run(*args, success=True):
        result = subprocess.run(["/bin/bash", "-s", "--", *args, "--no-panel"],
                                input=(repo_root / "docs/install.sh").read_text(),
                                env=env, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        assert not list(temporary.iterdir()), "Bootstrap left downloaded files behind"
        return result

    return home, env, run


def test_bootstrap_installs_and_reinstalls_detected_agents(bootstrap):
    home, _, run = bootstrap
    for agent in ("codex", "cursor", "claude"):
        (home / f".{agent}").mkdir()
    run("--all")
    runtime = home / ".code-gossip"
    assert (runtime / "VERSION").read_text().strip() == "1.2.3"
    assert not runtime.is_symlink()
    for agent in ("codex", "cursor", "claude"):
        assert document(home, agent)["hooks"]
    settings = runtime / "configs/config.json"
    settings.write_text('{"volume":17}')
    run("--all")
    assert json.loads(settings.read_text())["volume"] == 17


def test_bootstrap_forwards_selection_custom_home_and_dry_run(bootstrap):
    home, env, run = bootstrap
    env["CODEX_HOME"] = str(home / "custom codex")
    before = snapshot(home)
    run("--agents", "codex", "--dry-run")
    assert snapshot(home) == before
    run("--agents", "codex")
    assert (home / "custom codex/hooks.json").exists()
    assert not (home / ".codex").exists()
    assert not document(home, "cursor") and not document(home, "claude")


@pytest.mark.parametrize("failure", ["download", "archive", "jq", "platform", "--dev", "--de", "dev-install", "selection"])
def test_bootstrap_failures_preserve_home_and_clean_downloads(bootstrap, tmp_path, failure):
    home, env, run = bootstrap
    args = ["--agents", "codex"]
    if failure == "download":
        env["TEST_DOWNLOAD_FAIL"] = "1"
    elif failure == "archive":
        invalid = tmp_path / "invalid.zip"
        invalid.write_text("not a zip")
        env["TEST_PACKAGE"] = str(invalid)
    elif failure == "jq":
        (Path(env["PATH"]) / "jq").unlink()
    elif failure == "platform":
        uname = Path(env["PATH"]) / "uname"
        uname.unlink()
        uname.write_text("#!/bin/bash\necho Linux\n")
        uname.chmod(0o755)
    elif failure.startswith("--"):
        args.append(failure)
    elif failure == "dev-install":
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (home / ".code-gossip").symlink_to(checkout, target_is_directory=True)
    else:
        args = []
    before = snapshot(home)
    run(*args, success=False)
    assert snapshot(home) == before
    if failure == "dev-install":
        assert (home / ".code-gossip").resolve() == checkout
