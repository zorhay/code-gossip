# Code Gossip

**Hear your agents work.** Code Gossip turns Claude Code, Codex, and Cursor events into sound effects, spoken cues, and live AI commentary.

| Sound effects · Default | Senior | LLM narrator |
| :---: | :---: | :---: |
| [![Default sound effects following a login fix](docs/assets/demo-default.gif)](docs/assets/demo-default.mp4) | [![Senior voice cues following a login fix](docs/assets/demo.gif)](docs/assets/demo.mp4) | [![AI commentary following a login fix](docs/assets/demo-narrator.gif)](docs/assets/demo-narrator.mp4) |
| System sound cues · **[Listen →](docs/assets/demo-default.mp4)** | Fixed phrases · **[Listen →](docs/assets/demo.mp4)** | Contextual commentary · **[Listen →](docs/assets/demo-narrator.mp4)** |

One login fix, three ways to hear it. Click a demo for sound; GIF previews are silent. Narrator commentary is AI-written for this illustrated scenario; both voice demos use Kokoro.

**Shared agent hooks · Soundbar mixer · Effects + voice · Editable phrases · Optional AI narrator · macOS**

## Installation

### Install with your agent

**Recommended:** paste this into **Codex, Claude Code, or Cursor** on your Mac:

```text
Install https://github.com/zorhay/code-gossip for this agent. Follow the README and verify the installation.
```

**Upgrading to 0.5.0?** This is a breaking release with a new installation layout and no automatic migration. Follow the [upgrade steps](CHANGELOG.md#050---2026-10-11) before installing.

<details>
<summary><strong>Manual installation</strong></summary>

Requires macOS, Python 3, and jq. SoX enables generated effects.

```bash
brew install jq python
brew install sox          # optional

git clone https://github.com/zorhay/code-gossip.git
cd code-gossip
bash ./install.sh
```

Choose **all** detected agents, or multiple names/numbers such as `codex,cursor` or `2 3`. To skip the prompt:

```bash
bash ./install.sh --agents codex,claude
bash ./install.sh --all                  # every detected agent
bash ./install.sh --dry-run              # preview changes
```

For Codex, review and trust the commands in the CLI's `/hooks`, then start a new chat. Start a new session in your other selected agents too. Use the same `CODEX_HOME` when installing, updating, and removing a custom Codex setup.

Everything lives in `~/.code-gossip/`. The installer preserves settings and unrelated hooks; repeat installs do not duplicate integrations.

</details>

<details>
<summary><strong>Develop from a checkout</strong></summary>

```bash
bash ./install.sh --dev --agents codex,claude
```

This links `~/.code-gossip/` to the checkout's `code-gossip/` directory. Changes take effect directly; local preferences and runtime state stay gitignored. If a regular installation already exists, preserve any wanted settings, uninstall it, and remove the retained installation directory before switching to dev mode. Review new Codex hook commands in `/hooks`.

```bash
python3 -m pytest                         # full suite; requires pytest
python3 -m unittest tests.test_codex       # standard-library adapter tests
bash ./test-install.sh                    # validate the installed runtime
```

</details>

## Using Code Gossip

### Soundbar

Open the local mixer:

```bash
~/.code-gossip/soundbar/panel.sh
```

At [localhost:8111](http://localhost:8111), choose profiles, enable channels, set volumes, edit phrases, and preview events. Settings apply to all connected agents. Closing the mixer leaves hook audio running.

| Component | What it does | How to use it |
|---|---|---|
| **Effects** | System sounds, sampled audio, or generated tones | Pick a profile such as `paper`, `construction`, or `chiptune`; enable Effects. Generated profiles need SoX. |
| **Voice** | Spoken cues or commentary | Choose `senior` for editable phrases, `generals` for game-style clips, or `narrator` for AI commentary; enable Voice. |
| **Narrator** | Describes the current event in a chosen style | Select a provider/model, save credentials if needed, then use **Check connection** and **Test narration**. |
| **Speech engine** | Speaks Senior phrases and narrator text | Use built-in macOS speech, or select Kokoro and click **Install Kokoro**. |

Effects and Voice mix independently. A fresh install enables system effects and leaves Voice off. Repeat reduction skips rapid duplicate cues; previews bypass it. Codex approval audio has its own toggle.

The narrator supports Claude CLI, Anthropic, Gemini, OpenAI, and Ollama. It sends event context to the selected provider, which may charge for usage. Fixed phrases and sound effects need no LLM.

### Commands

```bash
~/.code-gossip/switch.sh                          # status and available controls
~/.code-gossip/switch.sh voice-profile senior     # the demo's profile
~/.code-gossip/switch.sh voice on                 # enable spoken cues
~/.code-gossip/switch.sh effects-profile paper    # choose effects
~/.code-gossip/switch.sh effects off              # mute effects
~/.code-gossip/switch.sh voice off                # mute voice
```

To mute everything, disable both channels. Saved preferences, phrases, and narrator styles live in `~/.code-gossip/configs/`; narrator API keys are stored in `config.json`.

<details>
<summary><strong>Update or uninstall</strong></summary>

From the checkout:

```bash
git pull
bash ./install.sh                      # use --dev for a dev installation
bash ./uninstall.sh                    # select integrations to remove
bash ./uninstall.sh --all              # remove all without questions
bash ./uninstall.sh --all --purge      # also remove saved settings
```

Partial removal keeps the runtime for remaining integrations. Dev removal only unlinks the installation; checkout files and settings remain even with `--purge`. Codex may require review of changed hooks in `/hooks` and a new chat after an update.

</details>

<details>
<summary><strong>No sound?</strong></summary>

Try a Soundbar preview first. Check the channel toggle, volume, and output device. If previews work but agent events are silent, review the selected integration; for Codex, trust the hooks in `/hooks` and start a new chat. For narration, use **Check connection** and **Test narration**.

```bash
bash ./test-install.sh
python3 ~/.code-gossip/engine/narrate.py --check-tts
bash ~/.code-gossip/data/sounds/generals/generate.sh  # regenerate missing clips
```

Only mapped events play. A completion cue means the current turn ended; it does not certify the whole task is complete.

</details>

[Architecture](ARCHITECTURE.md) · [Sound-design skill](dev-skills/sound-design/SKILL.md) · [Docs skill](dev-skills/maintain-docs/SKILL.md) · [Changelog](CHANGELOG.md)

Scripts: MIT. Bundled sampled audio: CC0. Default effects use macOS system sounds. Generals clips: generated with macOS speech. Demos use the shipped Default effects, AI-written narrator commentary, and Senior phrases; regenerate them with `python3 docs/render_demo.py` (Pillow, FFmpeg, and Kokoro installed in `code-gossip/state/.venv`; set `DEMO_KOKORO_PYTHON` for another location).
