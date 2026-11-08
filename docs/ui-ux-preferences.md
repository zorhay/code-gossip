# UI/UX preferences

These are the project design preferences agreed during Soundbar UI work. Coding agents and contributors should read this file before changing the interface, including in later sessions. Apply the same conventions to new controls and related screens. A newer explicit user request takes precedence; update this file when an agreed preference changes.

This file holds design intent and acceptance criteria. [Using Code Gossip](usage.md#soundbar) describes product behavior; [Soundbar architecture](../ARCHITECTURE.md#soundbar-and-its-api) describes implementation. These preferences are repository documentation, separate from personal runtime settings in `configs/`.

## Visual hierarchy and controls

| Area | Preference |
|---|---|
| Main feature navigation | Make Effects, Clips, Phrases, and AI commentary prominent through color and background. Give the selected tab a solid theme accent with contrasting text and icon; tint the surrounding navigation surface. Keep the established compact layout. |
| Selection and activation | Make the selected tab visually clear while keeping the separate **In use** indication. Browsing a feature and activating its audio are distinct states. |
| Action buttons outside the feature tabs | Use thin outlines and transparent backgrounds so the surrounding surface shows through. Match borders to the button's foreground color; primary actions use the theme accent. Keep explicit hover, disabled, and playing states. |
| Dropdown arrows | Use small gray arrows at 80% opacity. Match the arrow's right inset to the text's left inset, and reserve enough space so text cannot overlap the arrow. Apply this consistently to every dropdown. |
| Feature icons | Keep the navigation icons prominent and consistent in size. Reuse the existing SVG icon system. |
| Master volume | Size the speaker icon to balance the neighboring controls. Center the contents with equal top and bottom padding, and balance the outer horizontal insets. |
| Stable layout | Reserve space for alternate labels such as **Sound on/off** and **In use/Muted**. State changes must not shift the control group or neighboring panels horizontally. |
| Themes | Use the existing theme tokens for surfaces, text, and accents. Preserve the same hierarchy in Amber and Mint. |
| Status text | Keep status strips and badges to one or two words: **Ready**, **Detected**, **Connected**, **Loading…**, or **Load failed**. Let nearby labels identify the provider or engine; avoid repeating those names in full sentences. Keep detailed progress and explanations in the relevant drawer, with actionable errors beside blocked controls. |

The accepted CSS baseline in [ui.html](../code-gossip/soundbar/ui.html) is **20.7 px** for feature icons, **22 px** for the volume icon, and **10.2 px** for dropdown arrows. Arrows use `#9e9e9e` at `0.8` opacity. Select insets are **11 px**, or **9 px** for compact voice selectors; the master control group uses **6 px** outer padding. These are the final sizes from the session, not instructions to apply the earlier percentage increases again. Keep shared styles consistent when deliberately changing these values.

## Actions and settings

- Apply interaction and visual decisions across all Soundbar sections. Use shared behavior for equivalent controls; validate Effects, Clips, Phrases, and AI commentary when changing a common pattern.
- Keep **Use** beside the section heading. Place **Save** and **Discard** with the edited content, below the editor; in Phrases, put them below the phrase rows. Do not regroup them beside Use.
- Keep saving and activation distinct. Save persists content edits; Use applies a selection. Browsing and previewing must preserve the active selection. Choosing another pack or commentary style shows **Use**, even when that mode is already active. Show **In use** in the panel header only when the browsed selection matches the active selection. Browsing packs, styles, or phrase events has no Save/Discard controls or unsaved-edits indicator. Saving or discarding edits must preserve the browsed selection and must not activate it. Use can save pending edits while explicitly activating a selection.
- In AI commentary, apply engine, speaker, and provider selections immediately. Save model and API-key edits on field change. Keep phrase edits, phrase engine/voices, and session context under draft/save behavior. Commentary styles follow the same browse/Use behavior as effect packs.
- Show the relevant speech or Kokoro error beside **Use** or **In use**. Keep one speech **Details** entry point in the bottom setup strip; avoid duplicating that button in the header. Describe the error where the blocked action is visible.

## Playback and asynchronous feedback

- Change the clicked preview button's icon while audio plays, then restore the play icon on completion or failure. Use a separate loading indication while AI text is being generated. Preserve the active indication through rerenders and tab changes, tied to the requested content and voices. Browsing another style, changing a voice, or editing/removing a phrase must not mark different content as playing.
- Keep the latest engine, voice, or provider selection visible while earlier saves finish. Apply responses in order without allowing an older response to overwrite a newer edit; failed requests must also respect newer edits.
- Preserve keyboard focus across every section during background saves and readiness polling, including lists, filters, and action buttons. Keep unchanged controls mounted; restore focus to the same logical control when its markup changes.
- Preserve phrase input focus, text selection, caret position, and draft text when background saves, previews, or setup checks finish. Refresh labels and status without rebuilding the active editor unnecessarily.
- Preserve unrelated drafts when shared speech settings change. A setting that saves immediately must not silently save phrase content or activate a mode.

## Installation progress

The session exposed a reporting limitation: a quiet log can accompany an active download. Do not describe an installation as stalled solely because no new log line appeared. Check whether the process and download are advancing before diagnosing a hang.

When improving the progress UI, distinguish elapsed time, time since the last log output, and actual transfer progress. Show measured bytes, total size, or transfer rate when available; do not invent a percentage or treat log silence as zero activity. Keep the current stage, timeout, failure details, and retry action understandable. Package installation exposes elapsed time and recent output. Model preparation additionally exposes file bytes and totals when known, and network-transfer bytes when reported; buffered transfer bytes must remain distinct from prepared-file bytes. Keep previews disabled until the model and selected voices are ready, and offer model retry separately from package repair.

## Implementation and validation map

| Work | Source or check |
|---|---|
| Shared colors, spacing, icons, and markup | [Soundbar HTML/CSS](../code-gossip/soundbar/ui.html) |
| Selection, saves, previews, and rendering | [Soundbar JavaScript](../code-gossip/soundbar/ui.js) |
| Setup and installation status | [Soundbar server](../code-gossip/soundbar/server.py), [integration installer](../code-gossip/engine/integrations.py) |
| Static demo | [Pages builder](../scripts/build_pages.py), [demo adapter](demo.js); reuse the real Soundbar interface |
| Browser regressions | [Soundbar UI tests](../tests/test_soundbar_ui.cjs) |
| Installation and live API flows | [Soundbar end-to-end tests](../tests/test_soundbar_e2e.cjs) |
| Documentation upkeep | [maintain-docs skill](../dev-skills/maintain-docs/SKILL.md) |

For affected UI changes, verify both themes and desktop/narrow layouts. Check selected versus in-use tabs, dropdown insets, outlined actions, and mute/unmute geometry. Exercise preview generation, playback, completion, and failure. For asynchronous behavior, hold requests pending, make newer edits, and verify selection and typing survive both successful and failed responses. Use mocked APIs or disposable installs so validation does not alter personal settings. Follow [AGENTS](../AGENTS.md#validation) for the relevant commands.
