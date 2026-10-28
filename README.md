# Code Gossip

**Hear your agents work.** Code Gossip turns Claude Code, Codex, and Cursor events into sound effects, spoken cues, and live AI commentary.

**[▶ Try the live demo](https://zorhay.github.io/code-gossip/)** — explore Soundbar, hear evolving Wood Thrush melodies and prerecorded Kokoro voices, or play an example coding session.

**Shared agent hooks · Soundbar · Effects, clips, phrases & AI commentary · Editable phrases · Optional AI narrator · macOS**

## Installation

```bash
curl -fsSL https://zorhay.github.io/code-gossip/install.sh | bash -s -- --all
```

Requires macOS, Python 3, and jq. Installs for all detected agents; setup options are below.

### Install with your agent

> [!TIP]
> **Recommended: install with your agent.** Copy this prompt into **Codex, Claude Code, or Cursor** on your Mac:
>
> ```text
> Install https://github.com/zorhay/code-gossip for this agent.
> Use the latest stable release's code-gossip.zip package.
> Follow the README and verify the installation.
> ```

**Existing normal installation without `~/.code-gossip/current`?** Uninstall and reinstall once using the [steps below](#existing-flat-installations). Saved settings are retained; there is no automatic layout migration.

**Upgrading from before 0.5.0?** The installation layout changed in 0.5.0, with no automatic migration. Follow the [upgrade steps](CHANGELOG.md#050---2026-10-11) before installing.

<details>
<summary><strong>Manual installation</strong></summary>

Requires macOS, Python 3, and jq. SoX enables generated effects.

Install prerequisites if needed, then run the command above:

```bash
brew install jq python
brew install sox          # optional
```

The one-command installer downloads the latest stable release package, installs for every detected agent, and removes the temporary download. It requires the release workflow to have finished uploading the package. The command executes a downloaded script; [inspect it first](https://zorhay.github.io/code-gossip/install.sh) if preferred.

Replace `--all` with `--agents codex,claude` to choose agents, or add `--dry-run` to preview changes. These options also work from an extracted release package:

```bash
bash ./install.sh --agents codex,claude
bash ./install.sh --all                  # every detected agent
bash ./install.sh --dry-run              # preview changes
```

Without a selection flag, the extracted installer prompts for names or numbers. Piped installation needs `--all` or `--agents`; development installation requires a permanent checkout as described below.

For Codex, review and trust the commands in the CLI's `/hooks`, then start a new chat. Start a new session in your other selected agents too. Use the same `CODEX_HOME` when installing, updating, and removing a custom Codex setup.

Installation starts Soundbar in the background and opens it in your browser. Reinstallation restarts its existing panel to load updates. Use `--no-panel` to leave a stopped panel closed; an already running panel still restarts. Updates always verify the new panel before committing.

The runtime, settings, and state live in `~/.code-gossip/`. Installs prepare a complete release before switching to it. The installer preserves settings and unrelated hooks; repeat installs do not duplicate integrations. A failed install restores the prior release and settings; rerun the installer if an interruption leaves recovery pending.

Normal installation and updates use the same published package. Running `install.sh` without `--dev` from a source checkout downloads the latest stable package first; it does not install unreleased checkout code. GitHub's automatic **Source code** downloads are not installation packages.

</details>

<details>
<summary><strong>Develop from a checkout</strong></summary>

```bash
git clone https://github.com/zorhay/code-gossip.git
cd code-gossip
bash ./install.sh --dev --agents codex,claude
```

This links `~/.code-gossip/` to the checkout's `code-gossip/` directory. Changes take effect directly; local preferences and runtime state stay gitignored. Development installs work without a release package or network access and report `development` as their version. If a regular installation already exists, preserve any wanted settings, uninstall it, and remove the retained installation directory before switching to dev mode. Review new Codex hook commands in `/hooks`.

```bash
python3 -m pytest                         # test dependencies: see AGENTS.md
python3 -m unittest tests.test_codex       # standard-library adapter tests
bash ./test-install.sh                    # validate the installed runtime
```

</details>

## Using Code Gossip

### Soundbar

Installation opens Soundbar automatically. To open it again:

```bash
~/.code-gossip/soundbar/panel.sh
```

At [localhost:8111](http://localhost:8111), browse **Effects**, **Clips**, **Phrases**, or **AI commentary**. Browsing and previews leave the sounds agents play unchanged. The header shows what is in use. **Sound on/off** and volume apply immediately. **Settings** holds appearance, pacing, Codex approval cues, and updates.

| Category | Controls | Setup |
|---|---|---|
| **Effects** | Sound pack, event, and sample preview | Checks bundled files; generated packs require SoX |
| **Clips** | Generals recorded responses | Checks the bundled collection |
| **Phrases** | Editable Senior phrases, main-agent and subagent voices | Built-in macOS speech or optional Kokoro |
| **AI commentary** | Style, voice, and session context | Provider, model, optional API key, connection check, and speech engine |

Previews play the selected event and alternative. Phrases also have per-row playback. AI commentary’s **Play sample** generates and plays a sample on the first click; replaying the displayed text does not make another AI request.

**Save** writes the open tab without changing the active mode. Saving settings used by active audio requires its playback dependencies to be available. **Use** switches to a tab that has no unsaved edits. **Save & use** writes those edits and switches to that tab. A dot marks unsaved edits; the tab in use is labeled. **Discard** drops unsaved edits.

Each tab keeps setup in a details drawer. Effects, clips, and speech are checked for the visible tab. Cloud provider checks run only when you ask, because they can be billed. Claude CLI and Ollama may be checked when AI commentary is open. **Play sample** also verifies the provider. Kokoro installs only when you click **Install Kokoro**. SoX setup shows the installation command to run in your terminal. Using a tab selects one channel and preserves mute. Existing combined Effects + Voice settings remain unchanged until you use a tab; the CLI still supports independent channels.

**Settings → Appearance** switches between Amber and Mint; the choice stays in this browser. **Settings → Close Soundbar** stops the panel server; closing the browser tab alone leaves it running. Hook audio continues either way. **?** opens Getting started. Choosing a topic jumps to that part of the panel and does not save, play, or check anything.

The narrator supports Claude CLI, Anthropic, Gemini, OpenAI, and Ollama. It sends event context to the selected provider, which may charge for usage. A cloud connection check also makes a small generation request, and it runs only when you ask. Fixed phrases and sound effects need no LLM.

### Commands

```bash
~/.code-gossip/switch.sh                          # status and available controls
~/.code-gossip/switch.sh voice-profile senior     # the demo's profile
~/.code-gossip/switch.sh voice on                 # enable spoken cues
~/.code-gossip/switch.sh effects-profile paper    # choose effects
~/.code-gossip/switch.sh effects off              # mute effects
~/.code-gossip/switch.sh voice off                # mute voice
```

To mute everything in Soundbar, turn **Sound off**. From the CLI, disable both channels. Saved preferences, phrases, and narrator styles live in `~/.code-gossip/configs/`; narrator API keys are stored in `config.json`.

<details>
<summary><strong>Update or uninstall</strong></summary>

Soundbar checks GitHub for a newer stable release on startup when its last check is more than 24 hours old, then about once a day while the server runs. **Settings → Updates** shows the installed version, release notes, **Check for updates**, and **Update**. Updates install only when you choose them; closing the browser tab does not stop the server or its checks.

Both actions are also available from the installed runtime:

```bash
~/.code-gossip/update.sh check          # check GitHub immediately
~/.code-gossip/update.sh update         # download the release package, then run its installer
~/.code-gossip/update.sh status         # cached result and update progress
```

Updates use the release's `code-gossip.zip` asset in a temporary directory, so no Git checkout or Git executable is needed. Saved preferences, existing integrations, and custom samples referenced by `configs/sounds.json` are preserved. Use a distinct directory such as `data/sounds/custom/`; edits to shipped sample paths are replaced by the package. See [audio ownership rules](ARCHITECTURE.md#sound-manifest). Soundbar restarts and reconnects. Installation and verification failures switch back to the retained previous release and restore settings and owned hooks. If recovery itself fails, the previous release and journal stay available; retry **Update** or the installer after resolving the reported error. Settings edits are blocked while an install/update is running or recovery is pending. Progress and diagnostic logs live in `~/.code-gossip/version_state/`. Changed hook commands may require review in Codex CLI `/hooks` and a new agent session.

<a id="existing-flat-installations"></a>
**Existing flat installations:** normal installs without `~/.code-gossip/current` need an explicit reinstall. **Before uninstalling, back up your custom audio outside `~/.code-gossip/`.** Uninstall keeps settings but removes audio, logs, caches, and the Kokoro environment. Download and extract the latest release's **code-gossip.zip** asset, then run these commands from its `release/` directory:

```bash
bash ./code-gossip/uninstall.sh --all     # keep saved settings; omit --purge
bash ./install.sh --agents codex,claude   # select your existing integrations
```

After installation, restore your custom audio to its original `data/sounds/` paths and reinstall Kokoro from Soundbar if you use it. Use your existing custom `CODEX_HOME` for both commands, if any. This applies to `0.9.1` and earlier as well as flat installs made from later source checkouts. Unrelated hooks remain intact. Subsequent updates use release generations; development installs keep their checkout workflow.

Development installations continue to update from their checkout; release checks and installation are disabled in Soundbar's Updates section:

```bash
git pull
bash ./install.sh --dev                # select your existing integrations
```

Uninstall from the installed runtime:

```bash
~/.code-gossip/uninstall.sh            # select integrations to remove
~/.code-gossip/uninstall.sh --all       # remove all without questions
~/.code-gossip/uninstall.sh --all --purge # also remove saved settings
```

Partial removal keeps the runtime for remaining integrations. Dev removal only unlinks the installation; checkout files and settings remain even with `--purge`. Codex may require review of changed hooks in `/hooks` and a new chat after an update.

</details>

<details>
<summary><strong>No sound?</strong></summary>

Try a Soundbar preview first. Check Sound on/off, volume, and your output device. If previews work but agent events are silent, review the selected integration; for Codex, trust the hooks in `/hooks` and start a new chat. For narration, open the provider and speech drawers, then **Play sample**.

```bash
bash ./test-install.sh
python3 ~/.code-gossip/engine/narrate.py --check-tts
bash ~/.code-gossip/data/sounds/generals/generate.sh  # regenerate missing clips
```

Only mapped events play. A completion cue means the current turn ended; it does not certify the whole task is complete.

</details>

[Architecture](ARCHITECTURE.md) · [Sound-design skill](dev-skills/sound-design/SKILL.md) · [Docs skill](dev-skills/maintain-docs/SKILL.md) · [Changelog](CHANGELOG.md)

Scripts: MIT. Bundled sampled audio: CC0. Default effects use macOS system sounds. Generals clips: generated with macOS speech. Website phrase and commentary previews are prerecorded with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), whose model and inference code use Apache-2.0. Commentary examples are AI-written illustrations, not live provider responses. The [interactive homepage](https://zorhay.github.io/code-gossip/) and installer share the same released UI and shipped sound settings. See [website builds and recordings](ARCHITECTURE.md#website-builds-and-recordings) for regeneration, validation, and deployment.
