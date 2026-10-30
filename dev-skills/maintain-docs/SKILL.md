---
name: maintain-docs
description: Maintain Code Gossip documentation, demos, and development skills as the product changes. Use for documentation reviews, new documentation, or release notes in this repository.
---

# Maintain Code Gossip documentation

Keep documentation aligned with the implemented product and the reader's task. Work from the repository root; links below resolve from this skill's directory. This skill covers existing documents and future additions, not just a fixed list of filenames.

## Give each document a purpose

| Document | Keep here |
|---|---|
| [README](../../README.md) | Product introduction, demo link, quick installation, and links to documentation |
| [Installation options](../../docs/installation.md) | Prerequisites, manual installation, first session, and development setup |
| [Using Code Gossip](../../docs/usage.md) | Soundbar, audio modes, CLI commands, and troubleshooting |
| [Updates and removal](../../docs/updates.md) | Release updates, explicit reinstall steps, development updates, and uninstalling |
| [Licenses and credits](../../docs/credits.md) | Script/audio licenses and demo provenance |
| [ARCHITECTURE](../../ARCHITECTURE.md) | How the current implementation works: flows, boundaries, ownership, and data contracts |
| [CHANGELOG](../../CHANGELOG.md) | Notable changes users need to know, grouped by release |
| [AGENTS](../../AGENTS.md) | Concise contributor instructions and implementation conventions; link to deeper explanations |
| `TASKS.md` at the repository root | Brief descriptions of future tasks and ideas only; no current-work plans or decomposed solutions. Keep gitignored and out of commits, releases, and public links |
| `dev-skills/<skill-name>/SKILL.md` | Reusable instructions for a specific development activity; the folder name matches the frontmatter name |
| `docs/` | Supporting documents and reproducible demo sources/assets that need their own space |
| `docs/design/` | Requested feature designs: domain model, relationships, module contracts, and implementation status; link from architecture |

For a new document, choose its audience and purpose before adding it. Link it from the most relevant existing document. Keep an explanation in one primary location and cross-link instead of copying it into README, architecture, and skills. Add new enduring document roles to this table when needed.

## Preserve the presentation

**README:** Keep only a brief product introduction, a prominent live demo link, quick installation, and a list of links to the relevant documentation. Include a short, copyable “Install with your agent” prompt and the one-command installer. Keep detailed installation and development setup, usage, updates, troubleshooting, and credits in their supporting documents. Keep implementation details in architecture.

**Architecture:** Prefer readable Mermaid flows, sequences, state diagrams, package maps, and compact tables over long prose. Describe implemented behavior; keep brief future-task descriptions in local TASKS and current designs/implementation plans in dedicated `docs/design/` documents. Keep agent differences and important limitations visible. Link source for volatile lists and defaults instead of duplicating every value.

**Demo:** Follow one scenario with labeled event → sound/phrase transitions. Link to the interactive Soundbar demo at `https://zorhay.github.io/code-gossip/` from README. Keep profile previews on the demo site; label any GIF previews as silent. The homepage template lives in `docs/index.html`; `scripts/build_pages.py` embeds the real Soundbar UI and copies its script. `docs/demo.js` handles static prerecorded playback. Do not fork the dashboard markup or duplicate shipped sound settings. Playback requires a Play click and only one recording should play at a time.

Use `scripts/render_previews.py` with the Kokoro Python to regenerate website recordings after sound/default/style/catalog inputs change. The build rejects stale or missing recordings; do not bypass that gate. Wood Thrush uses a complete SoX-rendered phrase bank selected by the browser composer in `docs/melody.js`; run `tests/test_pages_melody.py` to verify parity with the Python composer and history expiry. Use [render_demo.py](../../docs/render_demo.py) only for README GIFs and older video assets. Preserve the requested scenario/profile unless the task changes it. Store AI-written narrator lines with provenance and distinguish them from live provider recordings. Both spoken demo modes use Kokoro. Run `node tests/test_pages.cjs` against `dist/pages` to verify actual audio, all-file decoding, controls, desktop/mobile layout, and project-subpath URLs. Keep Pages links relative. The release workflow builds and tests the website alongside the installer; the [deployment workflow](../../.github/workflows/pages.yml) verifies and deploys that exact artifact without rebuilding. Only publishing a release containing the changes updates the site. See [Architecture](../../ARCHITECTURE.md#website-builds-and-recordings) for build commands and required Pages settings. After an authorized release, verify the deployed version, source hashes, installer digest, and site playback. Demo generation must not change saved user preferences.

**Skills:** Keep each skill scoped to its development activity. Sound design lives in [sound-design](../sound-design/SKILL.md). Place future skills alongside it, with valid frontmatter and portable paths. Avoid adding product usage manuals to a skill.

## Ground changes in the code

Inspect the diff and affected implementation before documenting behavior. Useful sources include `code-gossip/installer.py` for install/removal, `hooks/` for agent routing, `engine/` for playback/narration, `soundbar/server.py` for API/event contracts, and `configs/*.defaults.json` and `data/sounds.json` for shipped content.

Check normal and dev installation separately. The product is Code Gossip; Soundbar is its local control panel. The shared installation is `~/.code-gossip/`, with `hooks/`, `engine/`, `soundbar/`, `data/`, `configs/`, and `state/`. Do not reintroduce legacy compatibility instructions or claim that settings migrate automatically.

Read shipped defaults, not personal settings or logs, when writing examples. Keep credentials and local runtime state out of documentation and staged files. Historical changelog entries may mention old names and paths; preserve them as history rather than treating them as current setup instructions.

## Maintain release history

Put pending user-visible changes under `Unreleased`, consolidating superseded entries into the final behavior. On an authorized release, move that section into the requested version with the actual release date, leaving an empty `Unreleased` heading for future work. Do not edit or commit `code-gossip/VERSION`: the [release workflow](../../.github/workflows/release.yml) generates it inside the installation package from the stable tag (with an optional `v` prefix). Preserve dated history; do not invent missing release notes.

Publish an authorized GitHub release using a stable version tag on the intended commit; the tag may be created beforehand or during publication. That publication triggers the workflow to build `code-gossip.zip`, test normal/development installs and updates, upload that exact asset to the existing release, and deploy Pages. Creating or pushing a tag alone does not run release packaging. Wait for the workflow to finish before treating the release as installable; reruns preserve an already-uploaded package. For local verification, run `python3 -B scripts/package_release.py <tag>` from the intended checkout, then `E2E_RELEASE_PACKAGE="$PWD/dist/code-gossip.zip" node tests/test_soundbar_e2e.cjs` with the browser dependencies described in AGENTS. The builder includes tracked runtime files and generates version metadata only in the package. Do not rewrite a candidate's `VERSION` in tests. After publication, verify GitHub's latest release, download its installation asset, and verify the installed version and site. See [Architecture](../../ARCHITECTURE.md#release-updates) for the shared package flow and the explicit uninstall/reinstall required by older flat installations.

Call out breaking changes prominently: what stops working, the affected users, and the supported upgrade steps. Reflect that notice in the release commit and annotated Git tag when releasing. Use the requested tag spelling; inspect existing tags and do not overwrite one. A documentation request alone does not authorize committing, pushing, tagging, or publishing a release.

## Review the result

- Check paths, commands, links, and anchors, including references after file moves. Resolve relative links from the containing document.
- Render changed Markdown and Mermaid diagrams when layout changes; check foldable sections, code blocks, and demo presentation.
- Validate skill frontmatter and referenced resources. Use the skill-creator validator if available.
- Run checks appropriate to changed behavior. Documentation alone usually needs link/render checks; executable demo changes also need regeneration and media validation.
- Before an authorized commit, inspect the staged diff and confirm `TASKS.md`, user settings, generated runtime files, and credentials are excluded. Report material limitations rather than implying unperformed checks passed.
