---
name: maintain-docs
description: Maintain Code Gossip documentation, demos, and development skills as the product changes. Use for documentation reviews, new documentation, or release notes in this repository.
---

# Maintain Code Gossip documentation

Keep documentation aligned with the implemented product and the reader's task. Work from the repository root; links below resolve from this skill's directory. This skill covers existing documents and future additions, not just a fixed list of filenames.

## Give each document a purpose

| Document | Keep here |
|---|---|
| [README](../../README.md) | Product introduction, demo, installation, and a compact usage reference |
| [ARCHITECTURE](../../ARCHITECTURE.md) | How the current implementation works: flows, boundaries, ownership, and data contracts |
| [CHANGELOG](../../CHANGELOG.md) | Notable changes users need to know, grouped by release |
| [AGENTS](../../AGENTS.md) | Concise contributor instructions and implementation conventions; link to deeper explanations |
| `TASKS.md` at the repository root | Local future work and ideas; keep gitignored and out of commits, releases, and public links |
| `dev-skills/<skill-name>/SKILL.md` | Reusable instructions for a specific development activity; the folder name matches the frontmatter name |
| `docs/` | Supporting documents and reproducible demo sources/assets that need their own space |

For a new document, choose its audience and purpose before adding it. Link it from the most relevant existing document. Keep an explanation in one primary location and cross-link instead of copying it into README, architecture, and skills. Add new enduring document roles to this table when needed.

## Preserve the presentation

**README:** Start with two sharp sentences, then the demo, a single feature line, and installation. Lead installation with a short, copyable “Install with your agent” prompt for Codex, Claude Code, or Cursor; keep manual and development setup in foldable sections. Keep the usage section short: components, how to use them, and useful commands. Name it for the activity (currently “Using Code Gossip”), not “Product guide”. Move detailed internals to architecture or a focused supporting document.

**Architecture:** Prefer readable Mermaid flows, sequences, state diagrams, package maps, and compact tables over long prose. Describe shipped behavior; future proposals belong in local TASKS. Keep agent differences and important limitations visible. Link source for volatile lists and defaults instead of duplicating every value.

**Demo:** Follow one scenario with labeled event → sound/phrase transitions. Keep Default, Senior, and LLM narrator previews in one compact README row, linking to the matching cards on `https://zorhay.github.io/code-gossip/`. Make the sound-demo link prominent and label GIF previews as silent. The actual players live in `docs/index.html`, with `player.css` and `player.js`; GitHub Pages serves `main` → `/docs` (`.nojekyll`). Native controls start unmuted and require a Play click; only one player should play at a time. Do not reintroduce GitHub attachment embeds, which force filename bars and muted playback.

Use [render_demo.py](../../docs/render_demo.py) to regenerate MP4s, silent GIFs, and WebP posters. Preserve the requested scenario/profile unless the task changes it. Store AI-written narrator lines with provenance and distinguish them from live provider recordings. Both voice demos use Kokoro. Verify timing, audio, captions, desktop/mobile layout, and one-click unmuted playback. Keep links relative inside the Pages site so its repository subpath works. After authorized publication, verify the deployed site and media; pushing regenerated assets updates the site without attachment uploads. Demo generation must not change saved user preferences.

**Skills:** Keep each skill scoped to its development activity. Sound design lives in [sound-design](../sound-design/SKILL.md). Place future skills alongside it, with valid frontmatter and portable paths. Avoid adding product usage manuals to a skill.

## Ground changes in the code

Inspect the diff and affected implementation before documenting behavior. Useful sources include `code-gossip/installer.py` for install/removal, `hooks/` for agent routing, `engine/` for playback/narration, `soundbar/server.py` for API/event contracts, and `configs/*.defaults.json` and `data/sounds.json` for shipped content.

Check normal and dev installation separately. The product is Code Gossip; Soundbar is its mixer. The shared installation is `~/.code-gossip/`, with `hooks/`, `engine/`, `soundbar/`, `data/`, `configs/`, and `state/`. Do not reintroduce legacy compatibility instructions or claim that settings migrate automatically.

Read shipped defaults, not personal settings or logs, when writing examples. Keep credentials and local runtime state out of documentation and staged files. Historical changelog entries may mention old names and paths; preserve them as history rather than treating them as current setup instructions.

## Maintain release history

Put pending user-visible changes under `Unreleased`, consolidating superseded entries into the final behavior. On an authorized release, move that section into the requested version with the actual release date, leaving an empty `Unreleased` heading for future work. Preserve dated history; do not invent missing release notes.

Call out breaking changes prominently: what stops working, the affected users, and the supported upgrade steps. Reflect that notice in the release commit and annotated Git tag when releasing. Use the requested tag spelling; inspect existing tags and do not overwrite one. A documentation request alone does not authorize committing, pushing, tagging, or publishing a release.

## Review the result

- Check paths, commands, links, and anchors, including references after file moves. Resolve relative links from the containing document.
- Render changed Markdown and Mermaid diagrams when layout changes; check foldable sections, code blocks, and demo presentation.
- Validate skill frontmatter and referenced resources. Use the skill-creator validator if available.
- Run checks appropriate to changed behavior. Documentation alone usually needs link/render checks; executable demo changes also need regeneration and media validation.
- Before an authorized commit, inspect the staged diff and confirm `TASKS.md`, user settings, generated runtime files, and credentials are excluded. Report material limitations rather than implying unperformed checks passed.
