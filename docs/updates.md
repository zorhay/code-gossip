# Updates and removal

[README](../README.md) · [Installation options](installation.md) · [Using Code Gossip](usage.md)

## Updates

Soundbar checks GitHub for a newer stable release on startup when its last check is more than 24 hours old, then about once a day while the server runs. **Settings → Updates** shows the installed version, release notes, **Check for updates**, and **Update**. Updates install only when you choose them; closing the browser tab does not stop the server or its checks.

Both actions are also available from the installed runtime:

```bash
~/.code-gossip/update.sh check          # check GitHub immediately
~/.code-gossip/update.sh update         # download the release package, then run its installer
~/.code-gossip/update.sh status         # cached result and update progress
```

Updates use the release's `code-gossip.zip` asset in a temporary directory, so no Git checkout or Git executable is needed. Saved preferences, existing integrations, and custom samples referenced by `configs/sounds.json` are preserved. Use a distinct directory such as `data/sounds/custom/`; edits to shipped sample paths are replaced by the package. See [audio ownership rules](../ARCHITECTURE.md#sound-manifest). Soundbar restarts and reconnects. Installation and verification failures switch back to the retained previous release and restore settings and owned hooks. If recovery itself fails, the previous release and journal stay available; retry **Update** or the installer after resolving the reported error. Settings edits are blocked while an install/update is running or recovery is pending. Progress and diagnostic logs live in `~/.code-gossip/version_state/`. Changed hook commands may require review in Codex CLI `/hooks` and a new agent session.

## Existing flat installations

Normal installs without `~/.code-gossip/current` need an explicit reinstall. **Before uninstalling, back up your custom audio outside `~/.code-gossip/`.** Uninstall keeps settings but removes audio, logs, caches, and the Kokoro environment. Download and extract the latest release's **code-gossip.zip** asset, then run these commands from its `release/` directory:

```bash
bash ./code-gossip/uninstall.sh --all     # keep saved settings; omit --purge
bash ./install.sh --agents codex,claude   # select your existing integrations
```

After installation, restore your custom audio to its original `data/sounds/` paths and reinstall Kokoro from Soundbar if you use it. Use your existing custom `CODEX_HOME` for both commands, if any. This applies to `0.9.1` and earlier as well as flat installs made from later source checkouts. Unrelated hooks remain intact. Subsequent updates use release generations; development installs keep their checkout workflow.

## Development installations

Development installations continue to update from their checkout; release checks and installation are disabled in Soundbar's Updates section:

```bash
git pull
bash ./install.sh --dev                # select your existing integrations
```

## Uninstall

Uninstall from the installed runtime:

```bash
~/.code-gossip/uninstall.sh            # select integrations to remove
~/.code-gossip/uninstall.sh --all       # remove all without questions
~/.code-gossip/uninstall.sh --all --purge # also remove saved settings
```

Partial removal keeps the runtime for remaining integrations. Dev removal only unlinks the installation; checkout files and settings remain even with `--purge`. Codex may require review of changed hooks in `/hooks` and a new chat after an update.
