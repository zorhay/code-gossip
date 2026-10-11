---
name: sound-design
description: Design Code Gossip sound profiles and spoken cues. Use when creating a sound theme, sourcing or editing audio, assigning event sounds, or writing Senior phrases and narrator styles.
---

# Code Gossip sound design

Design a coherent sound identity for coding-agent sessions: clear event cues, a consistent theme, and variation that stays comfortable during repeated use. This is a development skill for sound design. For toggles, volume, or selecting a built-in profile, use `~/.code-gossip/switch.sh`. Soundbar is the web mixer, launched with `~/.code-gossip/soundbar/panel.sh`.

Requests can use `create <profile>`, `find <query>`, or `add <profile> <event> <url>`, or describe the desired change in plain language.

## Work with the installed content

Resolve `~/.code-gossip/` first: a dev installation links into the checkout. Keep the user's existing profiles and preferences.

| Content | Location under the installation |
|---|---|
| Shipped sound mappings | `data/sounds.json` |
| Custom sound mappings | `configs/sounds.json` |
| Audio assets | `data/sounds/<profile>/` |
| Senior phrases | `configs/phrases.json` |
| Narrator style labels/prompts | `configs/narrator_styles.json` |

A custom sound manifest replaces the shipped manifest; it is not a partial merge. If no override exists, copy `data/sounds.json` to `configs/sounds.json` before adding a profile. Restart Soundbar after first creating an override because the server selects that file at startup.

Read the actual manifest for the current mapping format. The mixer event vocabulary lives in `soundbar/server.py` (`EVENTS`); use those categories instead of assuming every agent emits every event. The shipped Generals profile also maps the full vocabulary. Unmapped events stay silent.

## Design an event palette

Start from the scenario the user wants to hear. Give routine work a quieter texture, make approval and errors recognizable, and use completion cues for a clear handoff. Preserve any requested profile, voice, or theme. For a demo, follow one scenario and label the agent actions alongside the exact phrases or sounds being played.

## Create or change a profile

Use the user's theme, desired intensity, and selected events. If these are unspecified, choose a coherent, short, unobtrusive set of cues; ask only when a preference would materially change the result.

- Store samples in `data/sounds/<profile>/`; set the manifest profile's `dir` to `sounds/<profile>`.
- Under `effects.<profile>.events`, use `file` for one sample, `files` for random variants, `sequence` for alternative ordered groups with a `gap`, or `sox` for generated effects.
- File-based specs can use a `rate` range for variation. Keep routine cues brief and distinguish approval, error, and turn completion.
- Edit mappings in JSON. The engine is a generic dispatcher; sound design does not require new shell case blocks.
- User profiles belong in the override. For an explicitly requested shipped profile, edit the repository's `data/sounds.json` and update `EFFECTS_PROFILES` in `switch.sh` if CLI selection should support it.

Custom effects profiles are selectable in Soundbar. Do not change the active profile or enable a muted channel unless that is part of the user's request.

## Find and assign audio

For `find <query>`, locate audio with a license suitable for the intended use. Verify the license on the source page; a site's catalog may contain different licenses. Prefer CC0 for bundled samples and record provenance when adding assets.

For `add <profile> <event> <url>`, download the requested clip, verify it is playable audio, trim/fade as needed, and update that event's mapping while retaining the rest of the manifest. Use `sox` when available for editing. Preview at a moderate level.

## Phrases and narrator styles

Senior events contain lists of alternative strings. Subagent dialogue events contain lists of two-speaker pairs. Missing events can use shipped defaults; an explicit empty array means silence.

Narrator styles use `{ "label": "...", "prompt": "..." }` objects. Change persona or phrasing instructions there; the engine already appends speech-clarity rules. Do not copy API keys or runtime logs into shipped files.

## Verify the result

Validate edited JSON, confirm referenced samples exist, and listen to the changed events in Soundbar. Check that unrelated profiles remain present. For a reproducible engine preview without changing saved settings:

```bash
printf '{}\n' | FORCE_LAYER=effects FORCE_EFFECTS_PROFILE=paper \
  bash ~/.code-gossip/engine/play.sh edit
```

Replace the profile/event with the changed mapping. Report the files changed and how to select or preview the result.
