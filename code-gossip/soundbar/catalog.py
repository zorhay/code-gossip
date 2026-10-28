"""Shared Soundbar catalog for the local server and static website build.

This module only describes shipped content; it never reads user settings.
"""
from pathlib import Path

EVENTS = [
    "session_start", "edit", "bash", "search",
    "permission", "error", "subagent_start",
    "subagent_stop", "compact", "stop", "user_prompt",
    "read", "tool", "plan", "test", "build", "git",
    "git_status", "git_history", "git_commit", "git_push",
    "pre_compact", "session_end", "interrupt",
]

DIALOGUE_EVENTS = {"subagent_start", "subagent_stop"}
VOICE_PROFILES = ["senior", "narrator", "generals"]

NARRATOR_PROVIDERS = {
    "claude_cli": {
        "name": "Claude Code CLI",
        "description": "Uses your existing Claude Code auth. No extra setup needed.",
        "needs_key": False,
        "default_model": "haiku",
    },
    "anthropic": {
        "name": "Anthropic API",
        "description": "Direct Claude API. Requires key from console.anthropic.com",
        "needs_key": True,
        "default_model": "claude-haiku-4-5-20251001",
    },
    "gemini": {
        "name": "Google Gemini",
        "description": "Google AI. Requires key from aistudio.google.com",
        "needs_key": True,
        "default_model": "gemini-2.5-flash",
    },
    "openai": {
        "name": "OpenAI",
        "description": "OpenAI API. Requires key from platform.openai.com",
        "needs_key": True,
        "default_model": "gpt-4o-mini",
    },
    "ollama": {
        "name": "Ollama (local)",
        "description": "Local LLM via Ollama. No API key. Requires Ollama running.",
        "needs_key": False,
        "default_model": "qwen3.5:4b",
    },
}

TTS_ENGINES = {
    "say": {"name": "macOS Say", "description": "Built-in macOS TTS. No setup needed."},
    "kokoro": {"name": "Kokoro", "description": "Local neural TTS via background daemon. Keeps model warm for fast speech."},
}

KOKORO_VOICES = [
    {"id": "af_heart", "name": "Heart", "gender": "female"},
    {"id": "af_bella", "name": "Bella", "gender": "female"},
    {"id": "af_nicole", "name": "Nicole", "gender": "female"},
    {"id": "af_sarah", "name": "Sarah", "gender": "female"},
    {"id": "af_sky", "name": "Sky", "gender": "female"},
    {"id": "am_adam", "name": "Adam", "gender": "male"},
    {"id": "am_michael", "name": "Michael", "gender": "male"},
    {"id": "bf_emma", "name": "Emma (British)", "gender": "female"},
    {"id": "bf_isabella", "name": "Isabella (British)", "gender": "female"},
    {"id": "bm_george", "name": "George (British)", "gender": "male"},
    {"id": "bm_lewis", "name": "Lewis (British)", "gender": "male"},
]


def preview_catalog(sounds):
    """Expose sample identities, without shell commands or machine-local paths."""
    result = {}
    for layer, profiles in sounds.items():
        result[layer] = {}
        for name, profile in profiles.items():
            events = {}
            for event, spec in profile.get("events", {}).items():
                variants = spec.get("sequence") or [[name] for name in spec.get("files", [])]
                if not variants:
                    variants = [[spec["file"]]] if "file" in spec else [[]]
                events[event] = [" → ".join(Path(file).stem.replace("_", " ") for file in variant)
                                 or ("Evolving melody" if "melody" in spec else "Synthesized cue")
                                 for variant in variants]
            result[layer][name] = events
    return result
