"""Read provider model catalogs without generation, installs, or saved settings."""
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def list_models(provider, api_key=""):
    if provider == "claude_cli":
        return {"ok": True, "models": [], "supported": False,
                "message": "Claude CLI has no live model list. Enter a model or use the default."}
    endpoints = {
        "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": api_key, "anthropic-version": "2023-06-01"}),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": api_key}),
        "openai": ("https://api.openai.com/v1/models", {"Authorization": "Bearer " + api_key}),
        "ollama": ("http://localhost:11434/api/tags", {}),
    }
    if provider not in endpoints:
        return {"ok": False, "message": "Unknown provider"}
    if provider != "ollama" and not api_key.strip():
        return {"ok": False, "message": "Enter an API key to load models."}
    url, headers = endpoints[provider]
    params = {"limit": 1000} if provider == "anthropic" else {"pageSize": 1000} if provider == "gemini" else {}
    models, cursors = [], set()
    deadline = time.monotonic() + 30
    try:
        for _ in range(10):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            request = Request(url + ("?" + urlencode(params) if params else ""), headers=headers)
            with urlopen(request, timeout=min(10, remaining)) as response:
                data = json.load(response)
            entries = data["models" if provider in ("gemini", "ollama") else "data"]
            if not isinstance(entries, list):
                raise ValueError("Invalid model catalog")
            for entry in entries:
                name = entry.get("name" if provider in ("gemini", "ollama") else "id")
                if not isinstance(name, str) or not name:
                    continue
                if provider == "gemini":
                    if "generateContent" not in entry.get("supportedGenerationMethods", []):
                        continue
                    name = name.removeprefix("models/")
                if entry.get("lifecycle") == "retired":
                    continue
                # Catalogs without endpoint metadata can include non-language models.
                # The explicit connection check verifies the chosen model for narration.
                if provider in ("openai", "gemini") and any(part in name.lower() for part in (
                        "embedding", "moderation", "whisper", "tts", "transcri", "realtime", "audio", "image", "dall-e", "sora")):
                    continue
                models.append(name)
            cursor = data.get("last_id") if provider == "anthropic" and data.get("has_more") else data.get("nextPageToken") if provider == "gemini" else None
            if provider == "anthropic" and data.get("has_more") and not cursor:
                raise ValueError("Incomplete model catalog")
            if not cursor:
                return {"ok": True, "supported": True, "models": sorted(set(models))}
            if not isinstance(cursor, str) or cursor in cursors:
                raise ValueError("Invalid catalog pagination")
            cursors.add(cursor)
            params["after_id" if provider == "anthropic" else "pageToken"] = cursor
        raise ValueError("Model catalog is too large")
    except HTTPError as error:
        message = ("Model access denied. Check the API key and permissions." if error.code in (401, 403)
                   else "Model list is rate limited. Try again shortly." if error.code == 429
                   else "Could not load models from the provider. Try again.")
    except Exception:
        # Never return provider bodies or exception text: they may contain credentials.
        message = "Could not load models. Check the connection and try again."
    return {"ok": False, "message": message}
