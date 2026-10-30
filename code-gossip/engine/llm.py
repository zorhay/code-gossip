"""Shared provider transports. No settings, storage, narration, or speech dependencies."""
import json
import os
import shutil
import subprocess
import urllib.request

PROVIDERS = {
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

def _http_json(url, headers, body, timeout):
    """POST JSON, return parsed response."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_claude_cli(model, system, user, max_tokens=80, timeout=15):
    prompt = f"{system}\n\n{user}"
    result = subprocess.run(
        ["claude", "-p", "--model", model, prompt],
        capture_output=True, text=True, timeout=timeout,
        stdin=subprocess.DEVNULL, env={**os.environ, "CODE_GOSSIP_INTERNAL": "1"},
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _call_anthropic(model, api_key, system, user, max_tokens=80, timeout=5):
    result = _http_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01",
         "Content-Type": "application/json"},
        {"model": model, "max_tokens": max_tokens, "system": system,
         "messages": [{"role": "user", "content": user}]},
        timeout=timeout,
    )
    return result["content"][0]["text"].strip()


def _call_gemini(model, api_key, system, user, max_tokens=80, timeout=5):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    result = _http_json(
        url, {"Content-Type": "application/json"},
        {"system_instruction": {"parts": [{"text": system}]},
         "contents": [{"parts": [{"text": user}]}],
         "generationConfig": {"maxOutputTokens": max_tokens}},
        timeout=timeout,
    )
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_openai(model, api_key, system, user, max_tokens=80, timeout=5):
    result = _http_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {"model": model, "max_tokens": max_tokens,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        timeout=timeout,
    )
    return result["choices"][0]["message"]["content"].strip()


def _call_ollama(model, system, user, max_tokens=80, timeout=10):
    result = _http_json(
        "http://localhost:11434/api/chat",
        {"Content-Type": "application/json"},
        {"model": model, "stream": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}],
         "options": {"num_predict": max_tokens}},
        timeout=timeout,
    )
    return result["message"]["content"].strip()


def _dispatch(provider, model, api_key, system, user, max_tokens=80, timeout=None):
    """Low-level provider dispatch. Returns text or None."""
    meta = PROVIDERS.get(provider)
    if not meta:
        return None
    if not model:
        model = meta["default_model"]
    if provider == "claude_cli":
        return _call_claude_cli(model, system, user, max_tokens, timeout or 15)
    if provider == "anthropic":
        return _call_anthropic(model, api_key, system, user, max_tokens, timeout or 5)
    if provider == "gemini":
        return _call_gemini(model, api_key, system, user, max_tokens, timeout or 5)
    if provider == "openai":
        return _call_openai(model, api_key, system, user, max_tokens, timeout or 5)
    if provider == "ollama":
        return _call_ollama(model, system, user, max_tokens, timeout or 10)
    return None


def check_provider(provider, model, api_key):
    """Test if a provider is reachable/configured."""
    meta = PROVIDERS.get(provider)
    if not meta:
        return {"ok": False, "message": f"Unknown provider: {provider}"}

    if provider == "claude_cli":
        if shutil.which("claude"):
            return {"ok": True, "message": "claude CLI found in PATH."}
        return {"ok": False, "message": "claude CLI not found in PATH."}

    if provider in ("anthropic", "gemini", "openai"):
        if not api_key:
            return {"ok": False, "message": f"No API key configured. Get one from {meta['description'].split('from ')[-1]}"}
        if not model:
            model = meta["default_model"]
        try:
            _dispatch(provider, model, api_key, "You are a connection test.", "Reply with OK.", max_tokens=8)
            return {"ok": True, "message": f"Connected ({api_key[:8]}...)."}
        except Exception as e:
            msg = str(e)
            if "401" in msg or "403" in msg:
                return {"ok": False, "message": f"Invalid API key ({api_key[:8]}...)."}
            return {"ok": False, "message": f"Connection failed: {msg[:100]}"}

    if provider == "ollama":
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                count = len(data.get("models", []))
                return {"ok": True, "message": f"Ollama running, {count} model(s) available."}
        except Exception as e:
            return {"ok": False, "message": f"Cannot reach Ollama at localhost:11434: {e}"}

    return {"ok": False, "message": "Unknown provider."}


def client(config):
    """Bind provider settings to the shared TextRequest protocol."""
    def generate(request):
        result = _dispatch(config.get("narrator_provider", "claude_cli"),
                           config.get("narrator_model", ""), config.get("narrator_api_key", ""),
                           request.system, request.user, max_tokens=request.max_tokens, timeout=30)
        if not result or not result.strip():
            raise ValueError("Provider returned no text")
        return result.strip()
    return generate
