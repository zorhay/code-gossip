# Using Code Gossip

[README](../README.md) · [Installation options](installation.md) · [Updates and removal](updates.md)

## Soundbar

Installation opens Soundbar automatically. To open it again:

```bash
~/.code-gossip/soundbar/panel.sh
```

At [localhost:8111](http://localhost:8111), browse **Effects**, **Clips**, **Phrases**, or **AI commentary**. Browsing sound packs, phrases, and commentary styles leaves the sounds agents play unchanged; previews audition the current selection. The header shows what is in use. **Sound on/off** and volume apply immediately. **Settings** holds appearance, pacing, Codex approval cues, and updates.

| Category | Controls | Setup |
|---|---|---|
| **Effects** | Sound pack, event, and sample preview | Checks bundled files; generated packs require SoX |
| **Clips** | Generals recorded responses | Checks the bundled collection |
| **Phrases** | Editable Senior phrases, main-agent and subagent voices | Built-in macOS speech or optional Kokoro |
| **AI commentary** | Style, voice, and session context | Provider, model, optional API key, connection check, and speech engine |

Previews play the selected event and alternative. The clicked button shows a waveform until playback finishes, then returns to the play icon. If you browse or edit during playback, the indicator stays associated with the original content and voices. Phrases also have per-row playback. AI commentary’s **Play sample** generates and plays a sample on the first click; replaying the displayed text does not make another AI request.

Across all sections, browsing and activation are separate. Choose an effect pack or commentary style, then press **Use** in the header to apply it—even when that mode is already active. **In use** identifies the active selection. Browsing packs, styles, or phrase events does not create unsaved edits.

For editable content, **Save** and **Discard** sit below the editor, separate from **Use** in the header. In Phrases, they appear below the phrase rows. Save writes the edits without applying a browsed pack or style or switching modes; saving settings used by active audio requires its playback dependencies to be available. Discard reverts edits while preserving the browsed selection. Use saves any edits and activates that selection. A dot marks unsaved edits; the tab in use is labeled.

In AI commentary, the speech engine, speaker, and provider save immediately when selected. Model and API-key edits save when you leave the field. These settings apply to the runtime without switching modes; the speech engine and voices are shared with Phrases. Existing phrase edits are preserved. Failed saves restore the previous setting. Session-context edits use Save or Discard; style selections use Use.

Kokoro has two setup stages: installing its packages and preparing the speech model. After installation, Soundbar downloads and loads the model and selected voices when you open their speech mode. The speech drawer shows the current file, prepared bytes and total when known, and received bytes when reported by the downloader. Received bytes can advance before the model file is written. Previews remain disabled until the model and selected voices are ready. Reloading the panel resumes progress checks. A model-download failure offers **Retry model loading**; it does not require reinstalling the packages.

Each tab keeps setup in a details drawer. Effects, clips, and speech are checked for the visible tab. Cloud provider checks run only when you ask, because they can be billed. Claude CLI, Codex CLI, and Ollama may be checked when AI commentary is open. **Play sample** also verifies the provider. Kokoro installs only when you click **Install Kokoro**. During installation, the speech drawer shows recent package activity, elapsed time, and time since the last output. Package setup has a 20-minute limit; large downloads can be quiet between updates. After a failure, the latest output remains visible beside **Retry installation**. Speech errors appear beside Use (or the In use label); the bottom **Details** button opens installation and repair controls. SoX setup shows the installation command to run in your terminal. Using a tab selects one channel and preserves mute. Existing combined Effects + Voice settings remain unchanged until you use a tab; the CLI still supports independent channels.

**Settings → Appearance** switches between Amber and Mint; the choice stays in this browser. **Settings → Close Soundbar** stops the panel server; closing the browser tab alone leaves it running. Hook audio continues either way. **?** opens Getting started. Choosing a topic jumps to that part of the panel and does not save, play, or check anything.

The narrator supports Claude CLI, Codex CLI, Anthropic, Gemini, OpenAI, and Ollama. It sends event context to the selected provider, which may charge for usage. A cloud connection check also makes a small generation request, and it runs only when you ask. Fixed phrases and sound effects need no LLM.

For **Codex CLI**, install a recent CLI and sign in with `codex login`, then choose it in AI commentary’s provider drawer. No API key is required in Soundbar; generation uses your existing Codex authentication and its usage limits or billing. **Check CLI** only checks installation; **Play sample** verifies sign-in and model access. Leave Model blank for the CLI’s built-in default, or enter a model available to your account. Narration does not load your personal Codex configuration or project instructions. Each line runs in a temporary, ephemeral session with hooks disabled for that invocation. Requests time out after 15 seconds; timed-out events stay silent.

## Commands

```bash
~/.code-gossip/switch.sh                          # status and available controls
~/.code-gossip/switch.sh voice-profile senior     # the demo's profile
~/.code-gossip/switch.sh voice on                 # enable spoken cues
~/.code-gossip/switch.sh effects-profile paper    # choose effects
~/.code-gossip/switch.sh effects off              # mute effects
~/.code-gossip/switch.sh voice off                # mute voice
```

To mute everything in Soundbar, turn **Sound off**. From the CLI, disable both channels. Saved preferences, phrases, and narrator styles live in `~/.code-gossip/configs/`; narrator API keys are stored in `config.json`.

## No sound?

Try a Soundbar preview first. Check Sound on/off, volume, and your output device. If previews work but agent events are silent, review the selected integration; for Codex, trust the hooks in `/hooks` and start a new chat. For narration, open the provider and speech drawers, then **Play sample**.

From a source checkout, validate the installed runtime and speech setup:

```bash
bash ./test-install.sh
python3 ~/.code-gossip/engine/narrate.py --check-tts
bash ~/.code-gossip/data/sounds/generals/generate.sh  # regenerate missing clips
```

Only mapped events play. A completion cue means the current turn ended; it does not certify the whole task is complete.
