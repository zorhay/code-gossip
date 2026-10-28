# Code Gossip

**Hear your agents work.** Code Gossip turns Claude Code, Codex, and Cursor events into sound effects, spoken cues, and live AI commentary.

**[▶ Try the live demo](https://zorhay.github.io/code-gossip/)** — explore Soundbar, hear evolving Wood Thrush melodies and prerecorded Kokoro voices, or play an example coding session.

## Installation

Requires macOS, Python 3, and jq.

**Install with your agent:** copy this prompt into Codex, Claude Code, or Cursor:

```text
Install https://github.com/zorhay/code-gossip for this agent.
Use the latest stable release's code-gossip.zip package.
Follow the README and verify the installation.
```

**Or install for all detected agents:**

```bash
curl -fsSL https://zorhay.github.io/code-gossip/install.sh | bash -s -- --all
```

Installation opens Soundbar in your browser. For Codex, review and trust the commands in `/hooks`, then start a new chat. Start a new session in other selected agents too.

For prerequisites, agent selection, development setup, or older installations, see [installation options](docs/installation.md).

## Documentation

- [Using Code Gossip](docs/usage.md) — Soundbar, audio modes, and CLI commands.
- [Updates and removal](docs/updates.md) — releases, older installations, and uninstalling.
- [Troubleshooting](docs/usage.md#no-sound) — checks when audio is silent.
- [Architecture](ARCHITECTURE.md) — runtime, integrations, and data contracts.
- [Contributing](AGENTS.md) — project conventions and validation.
- [Sound design](dev-skills/sound-design/SKILL.md) · [Maintaining docs](dev-skills/maintain-docs/SKILL.md).
- [Changelog](CHANGELOG.md).
- [Licenses and credits](docs/credits.md).
