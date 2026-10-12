# Changelog

Notable user-visible changes to Code Gossip. Unreleased entries describe the current result; dated releases preserve the history of those versions.

## [Unreleased]

### Changed

- Soundbar now organizes Effects, Clips, Phrases, and AI commentary into four tabs, with an explicit Apply action and a separate active-selection indicator. Setup and previews operate on drafts without changing live preferences.
- Restored independent onboarding topic cards in a top-right column with 50%-opacity yellow-gold backgrounds. Each starts a separate guided scenario or dismisses independently; **?** restores the tips. Topics link to profile, engine, LLM, phrase, preview, and settings controls without changing the active selection.
- Setup checks run automatically after refresh and relevant changes, without saving drafts. Slow checks no longer block panel controls, and provider checks ignore unrelated speech settings.
- Kokoro checks detect broken environments and offer repair. Page loading uses lightweight file inventory, leaving expensive speech verification to the background check. Installation prevents panel shutdown while allowing the browser tab to close safely.
- Incomplete setup disables Apply with a reason and setup link; saving shows progress. Setup rows and installation messages share a consistent narrow-screen layout.
- Previews identify and play the selected event and alternative. **Play sample** generates and plays AI commentary, then reuses the sample for replay; provider and speech checks are independent, and installation progress survives a panel reload.
- Apply aligns to the right of the preview actions; active status remains above the tabs. Installation, verification, and provider connection have separate states and specific results, with consistent success/pending/failure colors. LLM suggestions load from live provider catalogs (installed models for Ollama), with refresh and manual entry; Claude CLI no longer shows a fixed model list.
- Compact per-category setup replaces the mixer table and onboarding tours. Existing combined audio remains intact until a mode is explicitly activated.
- Replaced the Claude-specific contributor document with a shorter `AGENTS.md` for all coding agents, linking to the detailed architecture and development skills.

### Added

- Independent main-agent and subagent Kokoro voices, including voice-correct draft previews.

## [0.6.0] - 2026-10-11

### Breaking changes

- Removed the `ambient`, `organic`, `chiptune`, and `factory` effects profiles. If any is selected in your saved settings, choose another Effects profile in Soundbar after updating; those profiles no longer produce cues.

### Added

- **CLOSE SOUNDBAR** stops the panel server from the UI, cleans up its PID file, and keeps agent hook audio running.
- Installation starts Soundbar in the background and opens its ready UI; `--no-panel` skips it for unattended setup. Reopening the panel reuses an existing server.
- First-visit welcome and a floating stack of dismissible amber tips with 50% background opacity and two-step highlights for profiles, mixer layers, Narrator LLM setup, Kokoro installation, and settings. Completed/dismissed suggestions stay hidden in the same browser.

### Changed

- Default appears first in the Effects profile selector and CLI profile list.
- Refined Construction and Paper samples and softened the Sci-fi tones.
- Reinstallation restarts the owned panel process so updated UI assets and server endpoints load together; ordinary panel opening reuses an existing server.

### Fixed

- Panel launch waits for a healthy server and reports startup/browser failures without undoing installation. Shutdown cleans up the listening socket and PID file.

## [0.5.1] - 2026-10-11

### Fixed

- Reserved turn/session ending cues for completion: tests and builds no longer reuse them across 10 effects profiles. Default now uses Tink for tests and Morse for builds; its demo is refreshed to match.
- Moved demo playback to GitHub Pages: clean players without filename bars, sound enabled on Play, and only one demo playing at a time. README previews link directly to each player; redundant captions are removed.

### Added

- Responsive demo page on GitHub Pages, serving repository videos directly with native controls and generated preview posters.
- Recommended “Install with your agent” option in README, with a copyable prompt for Codex, Claude Code, or Cursor; manual and development instructions remain foldable.
- Default sound-effects and AI-written narrator demos alongside the Senior demo, in a compact three-column README showcase. Each follows the same login-fix scenario with a silent GIF preview and a video with sound.

### Changed

- Demo generation supports individual profiles, reads Default cues from the shipped sound manifest, and voices saved narrator commentary with Kokoro. Compact previews show one event at a time for readability.

## [0.5.0] - 2026-10-11

### Breaking changes

**0.5.0 is a breaking release.** The installation layout and entrypoints have changed; legacy paths, settings formats, and automatic migration are no longer supported.

- All agents now share `~/.code-gossip/`, with hooks in `hooks/`, playback in `engine/`, and the mixer in `soundbar/`. Scripts or shortcuts targeting the old `~/.claude/soundbar/` layout must be updated.
- Separate agent installers are replaced by `install.sh` and `uninstall.sh` with agent selection. The root `SKILL.md` has moved to `dev-skills/sound-design/SKILL.md`.
- To upgrade an older installation: save any settings or custom audio you want to reference, use that version's uninstaller to remove its hooks and runtime, then install 0.5.0 using the [current instructions](README.md#installation). Recreate preferences in Soundbar; old settings files are not imported. Review changed Codex hooks in `/hooks` and start new agent sessions.
- Existing dev installations must be reinstalled from the new checkout layout. If already using `~/.code-gossip/` with the current layout, repeat the installer in the same mode; it preserves current-format settings.

### Added

- One installer and uninstaller for Codex, Cursor, and Claude, with interactive multi-selection, explicit `--agents`, `--all`, dry-run previews, and development mode.
- Codex lifecycle and tool audio, including tests, builds, reads, plans, Git status/history/commit/push, and explicit failures. Adapters normalize context for narration.
- Cursor user hooks for lifecycle, edits, shell/MCP completion, failures, subagent completion, and compaction, with Cursor-aware narration.
- Separate Codex approval-audio toggle that leaves permissions unchanged.
- Shared playback spacing across concurrent hooks, independent Effects/Voice cooldowns, important-cue handling, and previews that bypass spacing.
- Expanded Senior phrases and Generals clips for the full mixer event vocabulary.
- Optional narrator session memory with recent moments, compressed summaries, and automatic expiry; shared speech-clarity rules for every narrator provider.
- Documentation maintenance skill in `dev-skills/maintain-docs/` for current and future documents, demos, and release notes.
- A 12-second scenario following a login bug from search through review, using Senior phrases spoken by Kokoro; includes an MP4 with audio and a silent GIF preview.

### Changed

- Renamed the project to Code Gossip. Soundbar remains the name of its web mixer.
- Moved the runtime to `~/.code-gossip/`, organized into `hooks/`, `engine/`, `soundbar/`, `data/`, `configs/`, and `state/`. Personal settings and runtime files stay out of Git.
- Consolidated installation and removal in the shared installer. Selected agents get hooks independently; partial removal retains the runtime while other integrations use it.
- Updated the mixer branding, feedback states, and narrator controls.
- Shortened README to a two-sentence introduction, demo, feature line, foldable installation instructions, and concise usage reference. Replaced the architecture reference with current diagrams and data contracts.
- Corrected contributor guidance for the two audio channels, provider transports, and Kokoro runtime paths.
- Moved the sound-design skill to `dev-skills/sound-design/SKILL.md`, leaving room for additional development skills.

### Removed

- The old installation layout, automatic migration paths, old settings-format support, and the separate Codex install command. Installation uses only the current layout.

### Fixed

- Guarded hook entrypoints so cached commands do not block active chats after uninstallation.
- Preserve unrelated hook handlers and settings during idempotent installation and selective removal. Changed documents are backed up and replaced atomically.
- Do not let malformed settings for unselected agents block installation; inspect all supported hook documents before deleting the shared runtime.
- Validate panel/Kokoro process identity during removal, avoiding unrelated processes when PID files are stale.
- Distinguish successful Git mutations, dry runs, pending shell commands, and normal no-match searches in Codex audio.
- Use normalized Cursor events in narration without inventing shell exit codes.

## [0.3.0] - 2026-04-15

### Added
- **Kokoro TTS daemon** (`kokoro_server.py`): Unix socket server keeps Kokoro-82M model warm in memory. ~100-200ms per phrase instead of 3-5s cold starts. Auto-starts on first use, auto-shuts down after 10 minutes idle.
- **One-click Kokoro install** from the web panel with progress tracking
- **`integrations.json`** for persistent install state (kokoro_installed flag)
- **Rate variation** for sound specs: `"rate": [min, max]` randomizes `afplay -r` playback rate per play. Standard game audio technique for natural-sounding variety.
- **Soft pencil variants**: 4 new audio files processed from source material (low-pass filter + reverb)
- Variable-length sequence support in sound manifest (was hardcoded to 2 files)
- Server logging: config changes, playback events, persistence writes, errors, Kokoro install progress
- Senior profile connected to TTS engine system (Kokoro + say)

### Changed
- Voice profile renamed: `narration` → `senior`
- Paper profile overhauled: richer combinations for all events, rate variation on file-based specs
- `narrate.py` speaks via Kokoro daemon instead of importing PyTorch directly
- `_play_narration()` in server.py routes through TTS engine (was hardcoded to macOS say)

## [0.2.0] - 2026-04-12

### Added
- Sound manifest (`sounds.json`): single source of truth for all sound mappings, shared by hooks and UI
- Three spec types: `file`/`files` (sampled), `sox` (generated), `sequence` (multi-file)
- 12 effects profiles: ambient, attention, chiptune, construction, default, factory, minimal, organic, paper, sci-fi, submarine, silent
- Voice profiles from manifest (generals with command/response sequences)

### Fixed
- Locale-dependent volume: replaced `awk` floating-point math with pure bash integer arithmetic

## [0.1.0] - 2026-04-09

### Added
- Initial release: audio feedback plugin for Claude Code
- Three independent, mixable layers: effects, voice, narrator
- Hook-based event system (10 events)
- Web control panel (`server.py` + `ui.html`) with mixer layout
- CLI control (`switch.sh`)
- Narrator engine (`narrate.py`): 5 LLM providers, 5 narration styles
- TTS support: macOS say + Kokoro neural TTS
- Install/uninstall scripts with dry-run preview
- Installation validator (`test-install.sh`)
