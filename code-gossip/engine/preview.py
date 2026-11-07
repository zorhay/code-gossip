#!/usr/bin/env python3
"""Check/preview an in-memory Soundbar draft; never change saved preferences."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import narrate
from paths import executable


class SpeechUnavailable(RuntimeError):
    """A safe, actionable speech error for the control panel."""


def speak(text, config, role="main"):
    engine = config.get("tts_engine", "say")
    volume = int(config.get("voice_volume", 100))
    if engine == "kokoro":
        key = "kokoro_voice_sub" if role == "sub" else "kokoro_voice"
        voice = config.get(key, "am_adam" if role == "sub" else "af_heart")
        readiness = narrate.check_kokoro([voice], prepare=True)
        if not readiness["ok"]:
            raise SpeechUnavailable(readiness["message"])
        result = narrate._kokoro_request("speak", text=text, voice=voice, volume=volume)
        if not result or not result.get("ok"):
            raise SpeechUnavailable("Kokoro could not finish playback. Check model readiness and try again.")
    else:
        voice = config.get("voice_sub" if role == "sub" else "voice_main", "Aman" if role == "sub" else "Tara")
        fd, path = tempfile.mkstemp(suffix=".aiff", prefix="soundbar-preview-")
        os.close(fd)
        try:
            subprocess.run([executable("say") or "say", "-v", voice, "-r", "190", text, "-o", path], check=True, timeout=30, capture_output=True)
            subprocess.run([executable("afplay") or "afplay", "-v", str(volume / 100), path], check=True, timeout=45, capture_output=True)
        finally:
            os.unlink(path)


def run(request):
    config = request["config"]
    if request["check"]:
        scope = request.get("scope", "speech")
        if scope == "provider" and request["mode"] == "ai":
            result = narrate.check_provider(config["narrator_provider"], config["narrator_model"], config["narrator_api_key"])
            return {"ok": result["ok"], "message": "Connection ready" if result["ok"] else "Connection failed. Check provider, model, credentials, and network."}
        if scope != "speech":
            raise ValueError("Unknown setup check")
        if config["tts_engine"] == "kokoro":
            voices = [config.get("kokoro_voice", "af_heart")]
            if request["mode"] == "phrases":
                voices.append(config.get("kokoro_voice_sub", "am_adam"))
            return narrate.check_kokoro(voices, prepare=True, retry=request.get("retry") is True)
        return {"ok": bool(executable("say") and executable("afplay")), "message": "macOS speech unavailable"}
    role = request.get("role")
    if config.get("tts_engine") == "kokoro":
        voices = [config.get("kokoro_voice_sub", "am_adam")] if role == "sub" else [config.get("kokoro_voice", "af_heart")]
        if request["mode"] == "phrases" and not role and request.get("event") in ("subagent_start", "subagent_stop"):
            voices.append(config.get("kokoro_voice_sub", "am_adam"))
        readiness = narrate.check_kokoro(voices, prepare=True)
        if not readiness["ok"]:
            raise SpeechUnavailable(readiness["message"])
    if role:
        if role not in ("main", "sub"):
            raise ValueError("Unknown speaker")
        speak("Ready when you are.", config, role)
        return {"ok": True}
    if request["mode"] == "ai":
        action = request.get("action", "generate")
        if action == "generate":
            context = narrate.build_context({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/src/app.ts", "old_string": "const x = 1", "new_string": "const x = 2"}})
            text = narrate.call_provider(config["narrator_provider"], config["narrator_model"], config["narrator_api_key"], context, config["narrator_style"])
            if not text:
                raise RuntimeError("No commentary generated")
            return {"ok": True, "text": text}
        if action != "play" or not isinstance(request.get("text"), str) or not request["text"].strip() or len(request["text"]) > 4000:
            raise ValueError("Generate a sample before playback")
        speak(request["text"], config)
        return {"ok": True}
    event = request["event"]
    alternatives = request["phrases"].get(event, [])
    if not alternatives:
        return {"ok": True, "message": "This event has no phrases"}
    variant = request.get("variant", 0)
    if type(variant) is not int or not 0 <= variant < len(alternatives):
        raise ValueError("Unknown phrase alternative")
    phrase = alternatives[variant]
    roles = ["sub", "main"] if event == "subagent_stop" else ["main", "sub"]
    for text, speaker in zip(phrase if isinstance(phrase, list) else [phrase], roles):
        speak(text, config, speaker)
    return {"ok": True}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin))))
    except SpeechUnavailable as error:
        print(json.dumps({"ok": False, "message": str(error)}))
    except Exception:
        print(json.dumps({"ok": False, "message": "Could not check or play this draft. Check the selected engine and provider."}))
