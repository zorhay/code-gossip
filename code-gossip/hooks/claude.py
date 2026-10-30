#!/usr/bin/env python3
"""Observe Claude hooks independently of their optional sound classification."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import ROOT, ENGINE


EVENTS = {"Stop": "stop", "StopFailure": "error", "PermissionRequest": "permission",
          "SessionStart": "session_start", "SessionEnd": "session_end", "PreCompact": "pre_compact",
          "PostCompact": "compact", "SubagentStart": "subagent_start", "SubagentStop": "subagent_stop",
          "PostToolUseFailure": "error", "UserPromptSubmit": "user_prompt"}


def sound_event(data):
    event, tool = data.get("hook_event_name"), data.get("tool_name")
    if event in EVENTS:
        return EVENTS[event]
    if event == "PreToolUse":
        if tool in ("Edit", "Write"):
            return "edit"
        if tool in ("Grep", "Glob"):
            return "search"
    if event == "PostToolUse" and tool == "Bash":
        return "bash"
    return None


def dispatch(data, root=ROOT):
    if not isinstance(data, dict) or os.environ.get("CODE_GOSSIP_INTERNAL") == "1":
        return
    try:
        from engine.trajectory.runtime import observe
        observe("claude", data.get("hook_event_name", ""), data, root=root)
    except Exception:
        pass
    event = sound_event(data)
    if event:
        subprocess.run(["/bin/bash", str(ENGINE / "play.sh"), event], input=json.dumps(data), text=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)


def main():
    try:
        dispatch(json.load(sys.stdin))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    main()
