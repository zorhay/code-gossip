"""Hook format tests.

Validates Claude hook definitions: no trailing &, all events covered,
correct script reference, valid JSON.
"""

import json
import re

import pytest
import claude


# All 11 events the soundbar handles
ALL_EVENTS = {
    "stop", "edit", "bash", "search", "permission", "error",
    "subagent_start", "subagent_stop", "session_start", "compact",
    "user_prompt",
}


def _extract_hooks_json(claude_hooks_json):
    """Read the shipped Claude hook definitions used by the unified installer."""
    return json.loads(claude_hooks_json)


class TestHookFormat:
    """Hook command format validation."""

    def test_no_trailing_ampersand_in_hook_commands(self, claude_hooks_json):
        """Regression: play.sh backgrounds its own work; trailing & causes double-fork."""
        hooks = _extract_hooks_json(claude_hooks_json)
        for event_name, entries in hooks.items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert not cmd.rstrip().endswith("&"), (
                        f"Hook command for {event_name} has trailing '&': {cmd}\n"
                        f"play.sh handles its own backgrounding"
                    )

    def test_hook_commands_reference_adapter(self, claude_hooks_json):
        """All hook commands should use the observation/audio adapter."""
        hooks = _extract_hooks_json(claude_hooks_json)
        for event_name, entries in hooks.items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert "code-gossip/hooks/claude.py" in cmd, (
                        f"Hook for {event_name} doesn't reference code-gossip/hooks/claude.py: {cmd}"
                    )



class TestHookCoverage:
    """All 11 events must be covered by hooks."""

    def test_all_events_covered(self, claude_hooks_json):
        hooks = _extract_hooks_json(claude_hooks_json)

        covered_events = {claude.sound_event({"hook_event_name": event_name, "tool_name": tool})
                          for event_name in hooks for tool in ("Read", "Edit", "Write", "Grep", "Glob", "Bash")}

        missing = ALL_EVENTS - covered_events
        assert not missing, f"Events not covered by hooks: {missing}"


class TestHookJSON:
    """The shipped hook definitions must be valid, well-structured JSON."""

    def test_hooks_json_is_valid(self, claude_hooks_json):
        hooks = _extract_hooks_json(claude_hooks_json)
        assert isinstance(hooks, dict)

    def test_all_hooks_have_type_command(self, claude_hooks_json):
        hooks = _extract_hooks_json(claude_hooks_json)
        for event_name, entries in hooks.items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    assert hook.get("type") == "command", (
                        f"Hook for {event_name} has type '{hook.get('type')}', expected 'command'"
                    )

    def test_all_hooks_have_timeout(self, claude_hooks_json):
        hooks = _extract_hooks_json(claude_hooks_json)
        for event_name, entries in hooks.items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    assert "timeout" in hook, (
                        f"Hook for {event_name} missing timeout"
                    )
