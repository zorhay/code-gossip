#!/usr/bin/env python3
"""Narrator styles, manual previews, and the speech/check CLI.

Live commentary is composed from persistent trajectories by trajectory.runtime.
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import CONFIGS
from engine.llm import PROVIDERS, _dispatch, check_provider
from engine.speech import (speak, check_kokoro, TTS_ENGINES, KOKORO_VOICES,
                           KOKORO_SOCK, KOKORO_VENV)

_log = logging.getLogger("narrate")
CONFIG_FILE = CONFIGS / "config.json"
CONFIG_DEFAULTS = CONFIGS / "config.defaults.json"
STYLES_FILE = CONFIGS / "narrator_styles.json"
STYLES_DEFAULTS = CONFIGS / "narrator_styles.defaults.json"

# Fallback prompt used only if no styles file is available at all.
FALLBACK_STYLE_PROMPT = "You are a friendly pair programmer. Comment briefly on what the developer is doing — natural, supportive, sometimes amused."

PROMPT_PREFIX = "Narrate this coding moment in one short sentence: "

# Appended to every narrator system prompt. Output will be read aloud by TTS,
# so markdown syntax and URLs would be spoken literally and sound awful.
AUDIO_CLARITY_RULES = (
    "\n\nOutput plain spoken prose only — this will be read aloud by a TTS engine. "
    "Do NOT use any markdown or formatting: no asterisks, underscores, backticks, "
    "code blocks, hashes, brackets, bullet points, or numbered lists. "
    "Do NOT include URLs or full file paths; refer to files by their base name "
    "(e.g. \"app.ts\"), and omit links entirely. "
    "Do NOT write emoji, stage directions, parentheticals, or quote marks around the line. "
    "One short, conversational sentence that sounds natural when spoken."
)

def read_styles():
    """Read narrator styles (user file overrides defaults).

    Returns dict of {id: {"label": str, "prompt": str}}.
    """
    for path in (STYLES_FILE, STYLES_DEFAULTS):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def style_prompt(style_id):
    """Return the raw style prompt for a style id, with fallback."""
    styles = read_styles()
    s = styles.get(style_id) if style_id else None
    if isinstance(s, dict) and s.get("prompt"):
        return s["prompt"]
    # Fall back to pair_programmer default, then hardcoded string
    pp = styles.get("pair_programmer")
    if isinstance(pp, dict) and pp.get("prompt"):
        return pp["prompt"]
    return FALLBACK_STYLE_PROMPT


def build_system_prompt(style_id):
    """Return the full system prompt: style persona + audio-clarity constraints."""
    return style_prompt(style_id) + AUDIO_CLARITY_RULES

def read_config():
    for path in (CONFIG_FILE, CONFIG_DEFAULTS):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def _clip(text, limit):
    """Collapse whitespace and truncate with ellipsis. Empty input returns ""."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def build_context(data):
    """Extract a short narration-relevant string from hook event JSON."""
    event = data.get("hook_event_name", "")
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}

    if data.get("soundbar_agent") in ("codex", "cursor"):
        agent = "Cursor" if data["soundbar_agent"] == "cursor" else "Codex"
        kind = data.get("soundbar_event", "")
        lifecycle = {
            "session_start": f"{agent} session {data.get('source', 'startup')}.",
            "session_end": f"{agent} session closed.",
            "pre_compact": f"{agent} is preparing to compact the conversation context.",
            "compact": f"{agent} finished compacting the conversation context.",
            "interrupt": f"The user interrupted the current {agent} turn. Pause the work.",
        }
        if kind in lifecycle:
            return lifecycle[kind]
        if kind == "stop":
            message = _clip(data.get("last_assistant_message", ""), 250)
            return f"{agent} finished this turn." + (f" Final response: {message}" if message else "")
        if kind == "error":
            return f"{agent} encountered a failure: {_clip(data.get('error_message', ''), 250)}"
        if kind == "permission":
            reason = _clip(inp.get("description", inp.get("justification", "")), 180)
            return f"{agent} needs approval for {tool}." + (f" Reason: {reason}" if reason else "")
        if tool == "Bash":
            label = _clip(inp.get("description") or inp.get("command", ""), 180)
            verbs = {"test": "Ran tests", "build": "Ran a build", "git": "Ran a Git command",
                     "git_status": "Checked Git status", "git_history": "Read Git history",
                     "git_commit": "Created a Git commit", "git_push": "Finished a Git push",
                     "search": "Searched", "read": "Inspected files", "bash": "Ran a shell command"}
            resp = data.get("tool_response") or {}
            code = resp.get("exitCode")
            status = f" Exit code {code}." if code is not None else ""
            if data.get("soundbar_no_matches"):
                status = " No matches found; this is a normal search result."
            output = _clip(resp.get("stderr") or resp.get("stdout", ""), 200)
            return f"{agent} {verbs.get(kind, 'ran a command').lower()}: {label}.{status}" + (f" Output: {output}" if output else "")
        if kind in ("read", "search", "plan", "tool"):
            label = tool.split("__")[-1].replace("_", " ")
            details = _clip(json.dumps(inp, ensure_ascii=False), 250)
            verbs = {"read": "is inspecting", "search": "is searching with", "plan": "is planning with", "tool": "is using"}
            return f"{agent} {verbs[kind]} {label}. Details: {details}"

    if event == "SessionStart":
        return "New coding session started."

    if event == "UserPromptSubmit":
        prompt = _clip(data.get("prompt", ""), 250)
        if prompt:
            return f'User asked: "{prompt}"'
        return "User submitted a prompt."

    if event in ("SubagentStart", "SubagentStop"):
        atype = data.get("agent_type", "agent")
        verb = "spawned" if "Start" in event else "returned"
        return f"Sub-agent ({atype}) {verb}."

    if event == "Stop":
        message = _clip(data.get("last_assistant_message", ""), 250)
        return "Claude finished this turn." + (f" Final response: {message}" if message else "")

    if event in ("StopFailure", "PostToolUseFailure"):
        msg = data.get("error_message", "unknown error")[:120]
        return f"Error occurred: {msg}"

    if event == "PostCompact":
        return "Context was compacted (conversation got long)."

    if event == "PermissionRequest":
        return f"Asking permission to use {tool}."

    if tool in ("Edit", "Write"):
        fp = inp.get("file_path", "")
        parts = fp.rsplit("/", 2)
        short = "/".join(parts[-2:]) if len(parts) >= 2 else fp
        if tool == "Edit":
            old = _clip(inp.get("old_string", ""), 180)
            new = _clip(inp.get("new_string", ""), 180)
            if old or new:
                return f'Editing {short}. Old: "{old}". New: "{new}"'
            return f"Editing {short}"
        content = _clip(inp.get("content", ""), 300)
        if content:
            return f'Writing {short}. Content: "{content}"'
        return f"Writing {short}"

    if tool == "Bash":
        desc = _clip(inp.get("description", ""), 150)
        cmd = _clip(inp.get("command", ""), 150)
        label = desc or cmd or "(no command)"
        resp = data.get("tool_response") or {}
        if resp:
            exit_code = resp.get("exitCode", resp.get("exit_code"))
            stdout = _clip(resp.get("stdout", ""), 200)
            stderr = _clip(resp.get("stderr", ""), 200)
            status = f"exit {exit_code}" if exit_code is not None else "exit status unavailable"
            tail = ""
            if stderr:
                tail = f' Stderr: "{stderr}"'
            elif stdout:
                tail = f' Stdout: "{stdout}"'
            else:
                tail = " No output."
            return f'Ran "{label}" — {status}.{tail}'
        return f"Running: {label}"

    if tool in ("Grep", "Glob"):
        pattern = inp.get("pattern", "")
        return f"Searching for: {pattern[:150]}"

    if tool == "Read":
        fp = inp.get("file_path", "")
        parts = fp.rsplit("/", 2)
        short = "/".join(parts[-2:]) if len(parts) >= 2 else fp
        return f"Reading {short}"

    if tool == "Agent":
        desc = inp.get("description", "") or inp.get("prompt", "")[:100]
        return f"Delegating: {desc[:150]}"

    if tool:
        return f"Using {tool}."

    return f"Event: {event}" if event else ""


def call_provider(provider, model, api_key, context, style):
    """Generate an isolated preview without reading or updating live memory."""
    return _dispatch(provider, model, api_key, build_system_prompt(style), PROMPT_PREFIX + context)


def main():
    try:
        data = json.loads(sys.stdin.read())
        config = read_config()
        text = call_provider(config.get("narrator_provider", "claude_cli"), config.get("narrator_model", ""),
                             config.get("narrator_api_key", ""), build_context(data), config.get("narrator_style", "pair_programmer"))
        if text:
            engine = config.get("tts_engine", "say")
            voice = config.get("kokoro_voice", "af_heart") if engine == "kokoro" else config.get("voice_main", "Tara")
            speak(text, engine, voice, int(config.get("voice_volume", 100)))
    except Exception:
        _log.exception("Narrator preview failed")


if __name__ == "__main__":
    if "--check" in sys.argv:
        config = read_config()
        provider = config.get("narrator_provider", "claude_cli")
        model = config.get("narrator_model", "")
        api_key = config.get("narrator_api_key", "")
        result = check_provider(provider, model, api_key)
        print(json.dumps(result))
    elif "--check-tts" in sys.argv:
        config = read_config()
        engine = config.get("tts_engine", "say")
        if engine == "kokoro":
            print(json.dumps(check_kokoro()))
        else:
            print(json.dumps({"ok": True, "message": "macOS say is built-in."}))
    elif "--speak" in sys.argv or "--speak-sub" in sys.argv:
        # TTS mode: speak text from remaining args using configured engine
        # Usage: narrate.py --speak "text to speak"
        subagent = "--speak-sub" in sys.argv
        idx = sys.argv.index("--speak-sub" if subagent else "--speak")
        text = " ".join(sys.argv[idx + 1:])
        if not text:
            sys.exit(0)
        config = read_config()
        engine = config.get("tts_engine", "say")
        voice = config.get("kokoro_voice_sub" if subagent else "kokoro_voice", "am_adam" if subagent else "af_heart") if engine == "kokoro" \
            else config.get("voice_sub" if subagent else "voice_main", "Aman" if subagent else "Tara")
        volume = int(config.get("voice_volume", 100))
        speak(text, engine, voice, volume)
    elif "--dry-run" in sys.argv:
        try:
            data = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, ValueError):
            print("Error: invalid JSON on stdin", file=sys.stderr)
            sys.exit(1)
        config = read_config()
        provider = config.get("narrator_provider", "claude_cli")
        model = config.get("narrator_model", "")
        api_key = config.get("narrator_api_key", "")
        style = config.get("narrator_style", "pair_programmer")
        context = build_context(data)
        if not context:
            print("Error: no context extracted from event", file=sys.stderr)
            sys.exit(1)
        try:
            text = call_provider(provider, model, api_key, context, style)
            print(text or "")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        main()
