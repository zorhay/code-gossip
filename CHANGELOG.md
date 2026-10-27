# Changelog

Notable user-visible changes to Code Gossip. Unreleased entries describe the current result; dated releases preserve the history of those versions.

## [Unreleased]

### Added

- One-command macOS installation through the website bootstrap, using the same release package and installer as normal installation. The website includes a copyable command and displays the release version supplied by the deployment workflow.

### Fixed

- Reinstalls and updates carry forward custom audio referenced by `configs/sounds.json`, including after old releases are cleaned up. Unsafe paths, missing custom samples, or conflicting new package filenames stop before activation.
- Install/update failures retain a runnable release and durable recovery journal; settings writes are atomic, rollback is retryable, and obsolete code disappears from active paths. Concurrent Soundbar and CLI settings writes are rejected while installation or recovery is pending.
- All Soundbar POST endpoints require a same-origin UI request, and loopback Host validation blocks browser DNS rebinding. Uninstallation never follows a settings-directory symlink into unrelated files.

- Publishing a GitHub release now builds and attaches its installation package without trying to create the release again. Tag pushes alone do not publish; website deployment waits for the package, and reruns preserve an already-uploaded package.

### Changed

- Soundbar uses a compact list and detail layout. **Save** writes the open tab without changing the active mode; **Use** and **Save & use** switch what agents play. Amber and Mint live in **Settings → Appearance**. Cloud provider checks run only when you ask. **Getting started** replaces the topic-tip column.
- Normal installs and updates share one transaction: stage a complete release, atomically switch the active pointer, verify Soundbar, then commit. The previous release remains available for recovery.
- Normal installation and updating now use the same `code-gossip.zip` release package. The release workflow generates its `VERSION`, tests the package, and publishes it; version numbers are no longer edited in the source tree.
- Development installs remain local symlinks, work offline, and report `development`. Update them with `git pull` and `install.sh --dev`; Soundbar does not offer release replacement for a checkout.

### Breaking

- Existing flat normal installations (without `~/.code-gossip/current`), including `0.9.1` and earlier, require an explicit uninstall/reinstall. Use the new package’s uninstaller with `--all` **without `--purge`**, then install for your existing integrations and custom `CODEX_HOME`. Saved settings and unrelated hooks are retained. Back up custom audio outside the installation before uninstalling, restore it after reinstalling, and set up Kokoro again if used; uninstall removes audio and runtime state. See the [README steps](README.md#existing-flat-installations). There is no automatic layout migration; GitHub source archives are not installation packages.

## [0.9.1] - 2026-10-25

### Fixed

- The release now declares its matching version, allowing installed updaters to install it successfully. The published `0.9.0` archive incorrectly declared `0.8.0`, so updates were rejected before installation. Choose **Check for updates**, then **Update** in Soundbar, or run `~/.code-gossip/update.sh update`.
- Release validation checks the unmodified source archive against the intended tag. Update tests preserve the candidate archive's shipped version instead of replacing it in fixtures.

## [0.9.0] - 2026-10-25

### Added

- Update discovery in Soundbar with installed/available versions, release notes, and explicit check/update actions. The installed `update.sh` CLI shares the same flow: download fresh release source into a temporary directory, run its installer for existing integrations, restart and verify Soundbar, and attempt recovery on failure. Preferences, custom Codex paths, and unrelated hooks are preserved; local update records and logs live in `version_state/`. Older installations need one checkout-based reinstall to obtain the updater.

### Changed

- The Code Gossip marketing page deploys from the released commit when a GitHub release is published, instead of on every push or merge to `main`.

## [0.8.0] - 2026-10-22

### Added

- Wood Thrush (`wood-thrush`), a new effects profile with evolving melodies in a bounded minor pentatonic scale, favoring nearby notes and avoiding recent repeats with soft sine tones and reverb. Attention and completion retain distinct phrases; Soundbar previews have separate note history from live hooks. Available in Soundbar and the CLI; requires SoX.

### Fixed

- Soundbar onboarding cards stay within the viewport when mobile layout or scrolling moves the highlighted control below the screen.

## [0.7.0] - 2026-10-12

### Added

- Independent main-agent and subagent Kokoro voices, with previews using the selected speaker and phrase.
- Live model suggestions from Anthropic, Gemini, OpenAI, and locally installed Ollama models, with refresh and manual entry. Claude CLI keeps manual entry and its provider default.
- Six independent onboarding topics for profiles, sound engines, LLM setup, phrases, previews, and settings. Yellow-gold cards start guided scenarios on click, dismiss individually, and can be restored with **?**.

### Changed

- Soundbar replaces the mixer with **Effects**, **Clips**, **Phrases**, and **AI commentary** tabs. Browsing and previews use drafts; **Apply** explicitly activates the selection. Existing combined Effects + Voice settings remain intact until activation, and the CLI still supports independent channels.
- **Apply** sits beside preview controls, aligned right, and becomes green **Applied** for the active selection. Incomplete setup shows a reason and a setup link.
- Per-category setup separates installation, engine verification, and provider connection. Checks return to their original action label, with one separate colored result; provider and speech setup have their own foldouts.
- **Play sample** generates and plays AI commentary in one action, then replays the displayed sample without another AI request. Effects, clips, and phrase previews identify the selected event and alternative.
- Kokoro setup explains local dependencies and downloads, and offers repair after failed verification. Installation progress resumes after a browser reload; panel shutdown is blocked while installation runs.
- Replaced the Claude-specific contributor document with `AGENTS.md`, linked to architecture and development skills, and made agent-assisted installation prominent in the README.

### Fixed

- Setup checks run automatically after refresh, relevant draft changes, and installation completion without saving preferences. Provider checks no longer fail because of unrelated speech settings.
- Slow checks, previews, and model discovery no longer block panel controls. Initial page loading inventories local files without importing Kokoro; speech verification runs afterward.
- Kokoro verification detects broken environments instead of trusting a saved installation flag; repair reinstalls the existing environment's packages.

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
