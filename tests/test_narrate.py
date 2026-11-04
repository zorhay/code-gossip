"""Narrator tests.

Tests narrate.py functions without making network calls or playing audio.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOUNDBAR_DIR = REPO_ROOT / "code-gossip"

if str(SOUNDBAR_DIR) not in sys.path:
    sys.path.insert(0, str(SOUNDBAR_DIR))


class TestNarrateImport:
    """narrate.py must import cleanly."""

    def test_import_narrate(self):
        import narrate
        assert hasattr(narrate, "build_context")
        assert hasattr(narrate, "PROVIDERS")
        assert hasattr(narrate, "read_styles")
        assert hasattr(narrate, "style_prompt")


class TestProviders:
    """PROVIDERS dict completeness."""

    def test_has_all_five_providers(self):
        from narrate import PROVIDERS
        expected = {"claude_cli", "anthropic", "gemini", "openai", "ollama"}
        assert set(PROVIDERS.keys()) == expected

    def test_providers_have_required_keys(self):
        from narrate import PROVIDERS
        required = {"name", "description", "needs_key", "default_model"}
        for name, meta in PROVIDERS.items():
            missing = required - set(meta.keys())
            assert not missing, f"Provider '{name}' missing keys: {missing}"

    def test_providers_needs_key_types(self):
        from narrate import PROVIDERS
        # claude_cli and ollama don't need keys; the rest do
        assert PROVIDERS["claude_cli"]["needs_key"] is False
        assert PROVIDERS["ollama"]["needs_key"] is False
        assert PROVIDERS["anthropic"]["needs_key"] is True
        assert PROVIDERS["gemini"]["needs_key"] is True
        assert PROVIDERS["openai"]["needs_key"] is True


class TestCloudRequests:
    """Default models must produce speakable text within the caller's budget."""

    @pytest.mark.parametrize("budget", [8, 80, 160])
    @pytest.mark.parametrize("provider,model,response", [
        ("anthropic", "claude-haiku-5-5", {"content": [
            {"type": "thinking", "thinking": "Private reasoning"},
            {"type": "text", "text": " Ready"},
            {"type": "text", "text": " to go. "},
        ]}),
        ("gemini", "gemini-3.1-flash-lite", {"candidates": [{"content": {"parts": [
            {"thought": True, "text": "Private reasoning"},
            {"text": " Ready"}, {"text": " to go. "},
        ]}}]}),
        ("openai", "gpt-6-luna", {"choices": [{"message": {"content": " Ready to go. "}}]}),
    ])
    def test_default_requests(self, provider, model, response, budget):
        import narrate
        from server import NARRATOR_PROVIDERS

        with patch.object(narrate, "_http_json", return_value=response) as request:
            text = narrate._dispatch(provider, "", "test-key", "Speak briefly", "Edited app.py",
                                     max_tokens=budget, timeout=4)
        assert text == "Ready to go."
        assert NARRATOR_PROVIDERS[provider]["default_model"] == model
        url, headers, body = request.call_args.args
        assert request.call_args.kwargs["timeout"] == 4
        if provider == "anthropic":
            assert body["model"] == model
            assert body["max_tokens"] == budget
            assert body["thinking"] == {"type": "disabled"}
            assert body["output_config"] == {"effort": "low"}
        elif provider == "gemini":
            assert f"/models/{model}:generateContent" in url
            assert body["generationConfig"] == {
                "maxOutputTokens": budget, "thinkingConfig": {"thinkingLevel": "MINIMAL"}}
        else:
            assert body["model"] == model
            assert body["max_completion_tokens"] == budget
            assert body["reasoning_effort"] == "none"
            assert "max_tokens" not in body

    @pytest.mark.parametrize("provider,model,response", [
        ("anthropic", "claude-haiku-4-5-20251001", {"content": [{"type": "text", "text": "OK"}]}),
        ("gemini", "gemini-2.5-flash-lite", {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}),
        ("openai", "gpt-4o-mini", {"choices": [{"message": {"content": "OK"}}]}),
    ])
    def test_explicit_models_keep_their_request_settings(self, provider, model, response):
        import narrate

        with patch.object(narrate, "_http_json", return_value=response) as request:
            assert narrate._dispatch(provider, model, "test-key", "System", "User") == "OK"
        url, headers, body = request.call_args.args
        assert "thinking" not in body and "output_config" not in body
        assert "reasoning_effort" not in body
        if provider == "gemini":
            assert f"/models/{model}:generateContent" in url
            assert body["generationConfig"] == {"maxOutputTokens": 80}
        else:
            assert body["model"] == model
            assert body["max_tokens"] == 80

    @pytest.mark.parametrize("provider,response", [
        ("anthropic", {"content": [{"type": "thinking", "thinking": "Private reasoning"}]}),
        ("anthropic", {"content": [], "stop_reason": "refusal"}),
        ("gemini", {"candidates": [{"content": {"parts": [{"thought": True, "text": "Private reasoning"}]}}]}),
        ("gemini", {"candidates": []}),
        ("openai", {"choices": [{"message": {"content": None, "refusal": "Declined"}}]}),
    ])
    def test_no_answer_returns_no_speech(self, provider, response):
        import narrate

        with patch.object(narrate, "_http_json", return_value=response):
            assert narrate._dispatch(provider, "", "test-key", "System", "User") is None


class TestNarratorStyles:
    """Narrator styles are loaded from narrator_styles.defaults.json."""

    def test_includes_original_five_styles(self):
        from narrate import read_styles
        styles = read_styles()
        expected = {"pair_programmer", "sports", "documentary", "noir", "haiku_poet"}
        assert expected.issubset(set(styles.keys()))

    def test_styles_have_label_and_prompt(self):
        from narrate import read_styles
        styles = read_styles()
        for name, entry in styles.items():
            assert isinstance(entry, dict), f"Style '{name}' should be a dict"
            assert isinstance(entry.get("label"), str) and entry["label"], (
                f"Style '{name}' missing label"
            )
            assert isinstance(entry.get("prompt"), str) and len(entry["prompt"]) > 10, (
                f"Style '{name}' should have a non-trivial prompt"
            )

    def test_style_prompt_resolves_known_style(self):
        from narrate import style_prompt
        prompt = style_prompt("pair_programmer")
        assert isinstance(prompt, str) and len(prompt) > 10

    def test_style_prompt_falls_back_for_unknown(self):
        from narrate import style_prompt
        prompt = style_prompt("__definitely_not_a_real_style__")
        assert isinstance(prompt, str) and len(prompt) > 10


class TestBuildContext:
    """build_context() extracts narration-relevant context from event JSON."""

    def test_codex_turn_completion_is_not_task_completion(self):
        from narrate import build_context
        ctx = build_context({"soundbar_agent": "codex", "soundbar_event": "stop",
                             "last_assistant_message": "The first step is complete."})
        assert "finished this turn" in ctx
        assert "first step" in ctx
        assert "Task finished" not in ctx

    def test_codex_command_and_search_context(self):
        from narrate import build_context
        data = {"soundbar_agent": "codex", "soundbar_event": "test", "tool_name": "Bash",
                "tool_input": {"command": "uv run pytest -q"},
                "tool_response": {"exitCode": 0, "stdout": "All passed"}}
        ctx = build_context(data)
        assert "ran tests" in ctx and "All passed" in ctx
        data.update(soundbar_event="search", soundbar_no_matches=True)
        assert "normal search result" in build_context(data)
        data.update(soundbar_event="bash", soundbar_no_matches=False)
        data["tool_response"]["exitCode"] = None
        assert "Exit code None" not in build_context(data)

    def test_codex_lifecycle_and_tools_have_useful_context(self):
        from narrate import build_context
        cases = {
            "pre_compact": "preparing", "interrupt": "interrupted", "session_end": "closed",
            "plan": "planning", "read": "inspecting", "tool": "using",
        }
        for event, word in cases.items():
            ctx = build_context({"soundbar_agent": "codex", "soundbar_event": event,
                                 "tool_name": "mcp__docs__read_page", "tool_input": {"path": "src/app.py"}})
            assert word in ctx

    def test_session_start(self):
        from narrate import build_context
        ctx = build_context({"hook_event_name": "SessionStart"})
        assert "session" in ctx.lower() or "started" in ctx.lower()

    def test_edit_tool(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/home/user/src/components/App.tsx"},
        })
        assert "Editing" in ctx
        assert "App.tsx" in ctx

    def test_write_tool(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/home/user/README.md"},
        })
        assert "Writing" in ctx

    def test_bash_tool_with_description(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test", "description": "Run the test suite"},
        })
        assert "Run the test suite" in ctx

    def test_bash_tool_without_description(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        })
        assert "git status" in ctx

    def test_grep_tool(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Grep",
            "tool_input": {"pattern": "TODO"},
        })
        assert "TODO" in ctx

    def test_read_tool(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/project/src/main.py"},
        })
        assert "Reading" in ctx
        assert "main.py" in ctx

    def test_stop_event(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "Stop",
            "stop_reason": "end_turn",
        })
        assert "finished" in ctx.lower() or "done" in ctx.lower() or "end_turn" in ctx

    def test_error_event(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "StopFailure",
            "error_message": "Rate limit exceeded",
        })
        assert "error" in ctx.lower() or "Rate limit" in ctx

    def test_subagent_start(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "SubagentStart",
            "agent_type": "research",
        })
        assert "agent" in ctx.lower() or "spawned" in ctx.lower()

    def test_subagent_stop(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "SubagentStop",
            "agent_type": "research",
        })
        assert "returned" in ctx.lower() or "agent" in ctx.lower()

    def test_compact_event(self):
        from narrate import build_context
        ctx = build_context({"hook_event_name": "PostCompact"})
        assert "compact" in ctx.lower()

    def test_permission_event(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
        })
        assert "permission" in ctx.lower() or "Bash" in ctx

    def test_unknown_tool(self):
        from narrate import build_context
        ctx = build_context({
            "hook_event_name": "PreToolUse",
            "tool_name": "CustomTool",
            "tool_input": {},
        })
        assert "CustomTool" in ctx

    def test_empty_event(self):
        from narrate import build_context
        ctx = build_context({})
        assert ctx == ""


class TestCheckKokoro:
    """check_kokoro() returns correctly typed results."""

    def test_returns_dict_with_ok_and_message(self):
        from narrate import check_kokoro
        result = check_kokoro()
        assert isinstance(result, dict)
        assert "ok" in result
        assert "message" in result
        assert isinstance(result["ok"], bool)
        assert isinstance(result["message"], str)


class TestKokoroPaths:
    """Kokoro paths are under ~/.code-gossip/."""

    def test_kokoro_sock_path(self):
        from narrate import KOKORO_SOCK
        assert str(KOKORO_SOCK).endswith("code-gossip/state/kokoro.sock")
        assert KOKORO_SOCK.parent == SOUNDBAR_DIR / "state"

    def test_kokoro_venv_path(self):
        from narrate import KOKORO_VENV
        assert "code-gossip/state/.venv" in str(KOKORO_VENV)
