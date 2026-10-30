"""Boundary data shared by collectors, storage, and summary builders."""
from dataclasses import dataclass
import json
import re
import time


QUIET_SECONDS = 2.0
MAX_BATCH_SECONDS = 15.0
MAX_BATCH_EVENTS = 20
MAX_BATCH_BYTES = 24 * 1024
MAX_EVENT_BYTES = 64 * 1024


def clipped(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    half = max(0, (limit - 30) // 2)
    return text[:half] + "\n[...truncated...]\n" + text[-half:]


def payload_json(data):
    """Preserve the received payload, explicitly marking any size limit."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) <= MAX_EVENT_BYTES:
        return text
    return json.dumps({"truncated": True, "original_bytes": len(text.encode()),
                       "excerpt": clipped(text, MAX_EVENT_BYTES // 8)}, ensure_ascii=False)


def evidence_json(data):
    fields = ("prompt", "tool_name", "tool_input", "tool_response", "tool_output",
              "output", "error", "error_message", "exit_code", "last_assistant_message",
              "text", "command", "file_path", "edits", "agent_message", "status", "reason")
    selected = {key: data[key] for key in fields if key in data}
    text = json.dumps(selected, ensure_ascii=False)
    if len(text.encode()) > 8000:
        selected = {"truncated": True, "excerpt": clipped(text, 1900)}
    return json.dumps(selected, ensure_ascii=False)


@dataclass(frozen=True)
class Observation:
    agent: str
    session: str
    event: str
    turn: str
    prompt: str
    call: str
    actor: str
    process: str
    process_ref: str
    starts: bool
    ending: str
    urgent: bool
    source_id: str
    received: float
    payload: str
    evidence: str

    @classmethod
    def from_hook(cls, agent, event, data, now=None):
        if not isinstance(data, dict):
            return None
        sid = data.get("conversation_id") if agent == "cursor" else data.get("session_id")
        if not isinstance(sid, str) or not sid:
            return None  # A working directory is not a conversation identity.
        actor = str(data.get("agent_id") or data.get("subagent_id") or "")
        keys = ("parent_turn_id", "parent_prompt_id", "turn_id", "prompt_id", "generation_id")
        turn = next((str(data[key]) for key in keys
                     if data.get(key)), "")
        starts = event in ("UserPromptSubmit", "beforeSubmitPrompt")
        ending = {"Stop": "finished", "stop": "finished", "Interrupt": "interrupted",
                  "SessionEnd": "ended", "sessionEnd": "ended", "StopFailure": "failed"}.get(event, "")
        if event == "stop":
            ending = {"aborted": "interrupted", "error": "failed"}.get(data.get("status"), "finished")
        inp = data.get("tool_input") or {}
        resp = data.get("tool_response", data.get("tool_output")) or {}
        process = str(resp.get("session_id", "")) if isinstance(resp, dict) else ""
        if not process and isinstance(resp, str):
            match = re.search(r"Process running with session ID (\d+)", resp)
            process = match[1] if match else ""
        process_ref = str(inp.get("session_id", "")) if isinstance(inp, dict) else ""
        return cls(agent, sid, event, turn, str(data.get("prompt") or "") if starts else "",
                   str(data.get("tool_use_id") or data.get("call_id") or ""), actor, process, process_ref,
                   starts, ending, bool(ending or event == "PermissionRequest"),
                   str(data.get("event_id") or ""), time.time() if now is None else now,
                   payload_json(data), evidence_json(data))


@dataclass(frozen=True)
class TextRequest:
    purpose: str
    system: str
    user: str
    max_tokens: int = 500


@dataclass(frozen=True)
class BatchSummary:
    batch_id: int
    text: str


@dataclass(frozen=True)
class InteractionSummary:
    interaction_id: int
    through_batch: int
    text: str
