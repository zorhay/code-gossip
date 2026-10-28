# Installation options

[README](../README.md) · [Using Code Gossip](usage.md) · [Updates and removal](updates.md)

For the quick install command or a prompt to give your agent, see [README installation](../README.md#installation).

**Existing normal installation without `~/.code-gossip/current`?** Uninstall and reinstall once using the [explicit reinstall steps](updates.md#existing-flat-installations). Saved settings are retained; there is no automatic layout migration.

**Upgrading from before 0.5.0?** The installation layout changed in 0.5.0, with no automatic migration. Follow the [upgrade steps](../CHANGELOG.md#050---2026-10-11) before installing.

## Manual installation

Requires macOS, Python 3, and jq. SoX enables generated effects.

Install prerequisites if needed:

```bash
brew install jq python
brew install sox          # optional
```

Install the latest stable release:

```bash
curl -fsSL https://zorhay.github.io/code-gossip/install.sh | bash -s -- --all
```

The one-command installer downloads the latest stable release package, installs for every detected agent, and removes the temporary download. It requires the release workflow to have finished uploading the package. The command executes a downloaded script; [inspect it first](https://zorhay.github.io/code-gossip/install.sh) if preferred.

Replace `--all` with `--agents codex,claude` to choose agents, or add `--dry-run` to preview changes. These options also work from an extracted release package:

```bash
bash ./install.sh --agents codex,claude
bash ./install.sh --all                  # every detected agent
bash ./install.sh --dry-run              # preview changes
```

Without a selection flag, the extracted installer prompts for names or numbers. Piped installation needs `--all` or `--agents`; development installation requires a permanent checkout as described [below](#develop-from-a-checkout).

## First session

For Codex, review and trust the commands in the CLI's `/hooks`, then start a new chat. Start a new session in your other selected agents too. Use the same `CODEX_HOME` when installing, updating, and removing a custom Codex setup.

Installation starts Soundbar in the background and opens it in your browser. Reinstallation restarts its existing panel to load updates. Use `--no-panel` to leave a stopped panel closed; an already running panel still restarts. Updates always verify the new panel before committing.

## Installation behavior

The runtime, settings, and state live in `~/.code-gossip/`. Installs prepare a complete release before switching to it. The installer preserves settings and unrelated hooks; repeat installs do not duplicate integrations. A failed install restores the prior release and settings; rerun the installer if an interruption leaves recovery pending.

Normal installation and updates use the same published package. Running `install.sh` without `--dev` from a source checkout downloads the latest stable package first; it does not install unreleased checkout code. GitHub's automatic **Source code** downloads are not installation packages.

## Develop from a checkout

```bash
git clone https://github.com/zorhay/code-gossip.git
cd code-gossip
bash ./install.sh --dev --agents codex,claude
```

This links `~/.code-gossip/` to the checkout's `code-gossip/` directory. Changes take effect directly; local preferences and runtime state stay gitignored. Development installs work without a release package or network access and report `development` as their version. If a regular installation already exists, preserve any wanted settings, uninstall it, and remove the retained installation directory before switching to dev mode. Review new Codex hook commands in `/hooks`.

```bash
python3 -m pytest                         # test dependencies: see contributor guide below
python3 -m unittest tests.test_codex       # standard-library adapter tests
bash ./test-install.sh                    # validate the installed runtime
```

See the [contributor guide](../AGENTS.md#validation) for test dependencies and the full validation commands. To update a checkout, see [development updates](updates.md#development-installations).
