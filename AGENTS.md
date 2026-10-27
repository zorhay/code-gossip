# Contributor guide

Code Gossip adds audio feedback to Codex, Claude Code, and Cursor. Soundbar is its local control panel; the runtime supports independent Effects and Voice channels.

## Where things live

- `code-gossip/hooks/`: agent adapters; `engine/`: playback, narration, and Kokoro.
- `code-gossip/soundbar/`: UI, server, launcher, and setup tips.
- `code-gossip/data/`: shipped sound manifest and audio; `configs/`: defaults and local preferences; `state/`: local runtime files.
- `code-gossip/installer.py`: shared install/uninstall logic. Normal installs stage releases under `~/.code-gossip/version_state/releases/` and switch `current` atomically; dev installs symlink the checkout.

See [README](README.md) for usage and [ARCHITECTURE](ARCHITECTURE.md) for implementation details.

## Working rules

- Use [maintain-docs](dev-skills/maintain-docs/SKILL.md) for documentation and [sound-design](dev-skills/sound-design/SKILL.md) for audio content.
- Keep `TASKS.md`, user settings, credentials, and runtime state local and gitignored. Edit shipped defaults for product changes.
- Resolve runtime paths through `paths.py` or the package location. Honor the configured Python executable; hook environments may have a limited PATH.
- Preserve unrelated hooks and user settings. Never change agent permissions or trust settings. Keep the shared runtime while any integration remains.
- `play.sh` captures stdin and backgrounds playback. Do not add trailing `&` to hook commands or let audio failures block agent work.
- Use `data/sounds.json` as the shipped sound mapping. Keep profile lists in `switch.sh` and the server consistent. Reserve ending cues for completion; ordinary work must use different sounds.
- Keep hooks independent of the Soundbar server. Stopping the panel must leave hook audio working.
- Do not reintroduce legacy paths or automatic migration support.

## Validation

Run checks relevant to the change:

```bash
python3 -m pytest -q
python3 -m unittest tests.test_codex
node tests/test_soundbar_ui.cjs
node tests/test_soundbar_e2e.cjs
```

Python tests need pytest, pytest-subtests, and PyYAML. Browser tests need Node and Playwright with Chromium (`CHROMIUM_PATH` may override it). The end-to-end runner also needs macOS, Python, and jq; `E2E_PYTHON` selects Python. It uses disposable installs without downloading Kokoro, calling an LLM, or changing personal settings. For an installed runtime, `bash test-install.sh` checks files, hooks, and playback.
