# Using Code Gossip

[README](../README.md) · [Installation options](installation.md) · [Updates and removal](updates.md)

## Soundbar

Installation opens Soundbar automatically. To open it again:

```bash
~/.code-gossip/soundbar/panel.sh
```

At [localhost:8111](http://localhost:8111), browse **Effects**, **Clips**, **Phrases**, or **AI commentary**. Browsing and previews leave the sounds agents play unchanged. The header shows what is in use. **Sound on/off** and volume apply immediately. **Settings** holds appearance, pacing, Codex approval cues, and updates.

| Category | Controls | Setup |
|---|---|---|
| **Effects** | Sound pack, event, and sample preview | Checks bundled files; generated packs require SoX |
| **Clips** | Generals radio calls or [Empires](../code-gossip/data/sounds/empires/README.md) workers, scouts, scholars, and commanders | Checks the selected collection |
| **Phrases** | Editable Senior phrases, main-agent and subagent voices | Built-in macOS speech or optional Kokoro |
| **AI commentary** | Style, voice, and session context | Provider, model, optional API key, connection check, and speech engine |

Previews play the selected event and alternative. Phrases also have per-row playback. AI commentary’s **Play sample** generates and plays a sample on the first click; replaying the displayed text does not make another AI request.

**Save** writes the open tab without changing the active mode. Saving settings used by active audio requires its playback dependencies to be available. **Use** switches to a tab that has no unsaved edits. **Save & use** writes those edits and switches to that tab. A dot marks unsaved edits; the tab in use is labeled. **Discard** drops unsaved edits.

Each tab keeps setup in a details drawer. Effects, clips, and speech are checked for the visible tab. Cloud provider checks run only when you ask, because they can be billed. Claude CLI and Ollama may be checked when AI commentary is open. **Play sample** also verifies the provider. Kokoro installs only when you click **Install Kokoro**. SoX setup shows the installation command to run in your terminal. Using a tab selects one channel and preserves mute. Existing combined Effects + Voice settings remain unchanged until you use a tab; the CLI still supports independent channels.

**Settings → Appearance** switches between Amber and Mint; the choice stays in this browser. **Settings → Close Soundbar** stops the panel server; closing the browser tab alone leaves it running. Hook audio continues either way. **?** opens Getting started. Choosing a topic jumps to that part of the panel and does not save, play, or check anything.

The narrator supports Claude CLI, Anthropic, Gemini, OpenAI, and Ollama. It sends event context to the selected provider, which may charge for usage. A cloud connection check also makes a small generation request, and it runs only when you ask. Fixed phrases and sound effects need no LLM.

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
