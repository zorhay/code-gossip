"""Exercise the compression chain using evidence, fake text generation, and no audio."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from engine.trajectory.contracts import Observation, BatchSummary, InteractionSummary
from engine.trajectory.store import Store
from engine.trajectory.processor import Processor
from engine.trajectory import builders, runtime


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "trajectories.sqlite3")
    yield result
    result.close()


def add(store, event, now=100, agent="codex", session="one", **data):
    key = "conversation_id" if agent == "cursor" else "session_id"
    return store.collect(Observation.from_hook(agent, event, {key: session, **data}, now=now))


class Model:
    def __init__(self, narration="SILENT"):
        self.requests = []
        self.narration = narration

    def __call__(self, request):
        self.requests.append(request)
        return self.narration if request.purpose == "narration" else f"{request.purpose}: work toward the requested goal; outcome remains unverified."


def drain(store, sid, model, now=200, narrate=True):
    processor = Processor(store, model, narrate=narrate)
    for _ in range(100):
        if processor.step(sid, now) is None:
            return
    pytest.fail("Processor failed to become idle")


def test_two_persistent_trajectories_and_cross_interaction_context(store):
    sid = add(store, "UserPromptSubmit", turn_id="t1", prompt="Fix login")
    add(store, "PreToolUse", turn_id="t1", tool_name="Read", tool_input={"path": "auth.py"})
    model = Model()
    drain(store, sid, model, now=103)  # A quiet batch must be summarized before Stop arrives.
    add(store, "PostToolUse", now=104, turn_id="t1", tool_name="exec_command",
        tool_response={"exit_code": 1, "output": "Refresh race"})
    add(store, "Stop", now=105, turn_id="t1")
    add(store, "UserPromptSubmit", now=106, turn_id="t2", prompt="Keep the public API unchanged")
    add(store, "PostToolUse", now=107, turn_id="t2", tool_response={"exit_code": 0, "output": "tests pass"})
    add(store, "Stop", now=108, turn_id="t2")
    drain(store, sid, model)
    export = store.export(sid)
    assert len(export["interactions"]) == 2
    assert len(export["interaction_records"]) == 3
    assert len(export["session_records"]) == 2
    assert export["session"]["original_task"] == "Fix login"
    second = next(json.loads(r.user) for r in model.requests if r.purpose == "interaction"
                  and json.loads(r.user)["interaction_request"] == "Keep the public API unchanged")
    assert second["prior_session_trajectory"]["records"]
    assert second["original_session_task"] == "Fix login"
    assert all(n["status"] in ("silent", "superseded") for n in export["narrations"])


@pytest.mark.parametrize("agent,prompt,stop,turn_key", [
    ("claude", "UserPromptSubmit", "Stop", "prompt_id"),
    ("codex", "UserPromptSubmit", "Stop", "turn_id"),
    ("cursor", "beforeSubmitPrompt", "stop", "generation_id"),
])
def test_native_interaction_identity_and_raw_payload(store, agent, prompt, stop, turn_key):
    sid = add(store, prompt, agent=agent, **{turn_key: "a", "prompt": "Fix it"})
    add(store, "PostToolUse", agent=agent, **{turn_key: "a", "tool_response": {"content": [{"type": "text", "text": "Full result"}]}})
    add(store, stop, agent=agent, **{turn_key: "a"})
    drain(store, sid, Model())
    export = store.export(sid)
    assert export["interactions"][0]["source_id"] == "a"
    assert json.loads(export["events"][1]["payload"])["tool_response"]["content"][0]["text"] == "Full result"


def test_late_process_result_stays_with_original_interaction(store):
    sid = add(store, "UserPromptSubmit", prompt="First")
    add(store, "PostToolUse", tool_use_id="call1", tool_response={"session_id": 123, "output": "running"})
    add(store, "Stop")
    drain(store, sid, Model())
    add(store, "UserPromptSubmit", prompt="Second")
    add(store, "PostToolUse", tool_name="write_stdin", tool_input={"session_id": 123},
        tool_response={"exit_code": 0, "output": "done"})
    export = store.export(sid)
    assert export["events"][-1]["interaction_id"] == export["interactions"][0]["id"]
    drain(store, sid, Model())
    assert len(store.export(sid)["session_records"]) == 1


@pytest.mark.parametrize("poll_input", [None, {}, {"session_id": 123}])
def test_process_owner_wins_over_polling_turn_and_call(store, poll_input):
    sid = add(store, "UserPromptSubmit", turn_id="first", prompt="Run background tests")
    add(store, "PostToolUse", turn_id="first", tool_use_id="launch",
        tool_response={"session_id": 123, "output": "running"})
    add(store, "Stop", turn_id="first")
    drain(store, sid, Model())
    first = store.export(sid)["interactions"][0]["id"]
    previous = store.export(sid)["session_records"][0]["through_batch"]
    add(store, "UserPromptSubmit", now=201, turn_id="second", prompt="Inspect another file")
    if poll_input is not None:
        add(store, "PreToolUse", now=202, turn_id="second", tool_use_id="poll",
            tool_name="write_stdin", tool_input=poll_input)
    add(store, "PostToolUse", now=203, turn_id="second", tool_use_id="poll",
        tool_name="write_stdin", tool_input={"session_id": 123},
        tool_response={"exit_code": 0, "output": "background tests passed"})
    assert store.export(sid)["events"][-1]["interaction_id"] == first
    model = Model()
    drain(store, sid, model, now=206)
    request = next(json.loads(r.user) for r in model.requests
                   if r.purpose == "interaction" and "background tests passed" in r.user)
    assert request["interaction_request"] == "Run background tests"
    assert store.export(sid)["session_records"][0]["through_batch"] > previous
    assert store.export(sid)["interactions"][1]["request"] == "Inspect another file"


def test_call_owner_wins_over_current_turn_without_process_reference(store):
    sid = add(store, "UserPromptSubmit", turn_id="first", prompt="First")
    add(store, "PreToolUse", turn_id="first", tool_use_id="call1")
    add(store, "UserPromptSubmit", turn_id="second", prompt="Second")
    add(store, "PostToolUse", turn_id="second", tool_use_id="call1", tool_response={"output": "late"})
    result = store.export(sid)
    assert result["events"][-1]["interaction_id"] == result["interactions"][0]["id"]


def test_new_prompt_ignores_previous_tool_ownership(store):
    sid = add(store, "UserPromptSubmit", turn_id="first", prompt="First")
    add(store, "PostToolUse", turn_id="first", tool_use_id="call1", tool_response={"session_id": 123})
    add(store, "UserPromptSubmit", turn_id="second", prompt="Second", tool_use_id="call1",
        tool_input={"session_id": 123})
    result = store.export(sid)
    assert len(result["interactions"]) == 2
    assert result["events"][-1]["interaction_id"] == result["interactions"][1]["id"]


@pytest.mark.parametrize("repeats", [1, 1000])
def test_cursor_subagent_findings_reach_builder_with_size_bound(store, repeats):
    sid = add(store, "beforeSubmitPrompt", agent="cursor", generation_id="turn", prompt="Fix login")
    task = "Trace the expired-token retry"
    summary = "The retry reuses an expired token after TimeoutError. " * repeats
    add(store, "subagentStop", agent="cursor", generation_id="turn", subagent_type="explore",
        status="completed", task=task, description="Inspecting authentication", summary=summary,
        duration_ms=45000, message_count=12, tool_call_count=8, loop_count=0, modified_files=[])
    model = Model()
    drain(store, sid, model)
    request = next(json.loads(r.user) for r in model.requests if r.purpose == "interaction")
    evidence = next(e["evidence"] for e in request["batch_events"] if e["event"] == "subagentStop")
    text = json.dumps(evidence, ensure_ascii=False)
    assert task in text
    assert "retry reuses an expired token after TimeoutError" in text
    assert len(text.encode()) <= 8000
    assert bool(evidence.get("truncated")) == (repeats > 1)


def test_unknown_session_is_not_invented_and_unknown_interaction_is_retained(store):
    assert Observation.from_hook("codex", "PostToolUse", {"cwd": "/same/project"}) is None
    sid = add(store, "PostToolUse", tool_input={"cmd": "ls"})
    event = store.export(sid)["events"][0]
    assert event["interaction_id"] is None
    assert store.next_batch(sid) is None


def test_retries_do_not_duplicate_evidence_or_summaries(store):
    sid = add(store, "UserPromptSubmit", prompt="Fix", event_id="e1")
    add(store, "UserPromptSubmit", prompt="Fix", event_id="e1")
    add(store, "Stop")
    failing = Processor(store, Mock(side_effect=TimeoutError))
    with pytest.raises(TimeoutError):
        failing.step(sid, 200)
    assert len(store.export(sid)["events"]) == 2
    assert not store.export(sid)["interaction_records"]
    drain(store, sid, Model())
    drain(store, sid, Model())
    result = store.export(sid)
    assert len(result["interaction_records"]) == len(result["session_records"]) == 1


def test_concurrent_ingestion_and_session_isolation(store):
    sid = add(store, "UserPromptSubmit", turn_id="t", prompt="A")
    other = add(store, "UserPromptSubmit", session="two", turn_id="t", prompt="B")
    def collect(n):
        writer = Store(store.path)
        try:
            add(writer, "PostToolUse", turn_id="t", event_id=f"event{n}", tool_response={"output": str(n)})
        finally:
            writer.close()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(collect, range(40)))
    drain(store, sid, Model())
    assert len(store.export(sid)["events"]) == 41
    assert len(store.export(other)["events"]) == 1
    assert len(store.export(sid)["interaction_records"]) == 3


def test_pending_results_do_not_claim_success_and_grounding_is_in_prompt(store):
    sid = add(store, "UserPromptSubmit", prompt="Run tests")
    add(store, "PostToolUse", tool_response={"session_id": 99, "output": "running"})
    model = Model()
    drain(store, sid, model)
    request = next(r for r in model.requests if r.purpose == "interaction")
    assert "A tool starting is not success" in request.system
    assert "running" in request.user
    assert not store.export(sid)["session_records"]


def test_rollup_result_is_rejected_if_late_evidence_arrives(store):
    sid = add(store, "UserPromptSubmit", turn_id="t", prompt="Fix")
    add(store, "Stop", turn_id="t")
    processor = Processor(store, Model(), narrate=False)
    assert processor.step(sid, 200) == "batch"
    rollup = store.next_rollup(sid)
    add(store, "PostToolUse", now=201, turn_id="t", tool_response={"output": "late failure"})
    assert not store.commit_rollup(InteractionSummary(rollup["id"], rollup["through_batch"], "old"), 202)
    drain(store, sid, Model(), now=204)
    assert len(store.export(sid)["session_records"]) == 1


def test_compaction_keeps_records_and_recent_evidence(store):
    sid = add(store, "UserPromptSubmit", prompt="Fix")
    for n in range(8):
        add(store, "PostToolUse", now=100 + n * 20)
        batch = store.next_batch(sid)
        store.seal_due(sid, 120 + n * 20)
        store.commit_batch(BatchSummary(batch["id"], "evidence " * 220), 120 + n * 20)
    iid = store.export(sid)["interactions"][0]["id"]
    view = Processor(store, Model()).context("interaction", iid)
    assert len(view["records"]) == 4
    assert view["context"]
    assert len(store.export(sid)["interaction_records"]) == 8


def test_ingestion_needs_neither_provider_nor_speech(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/config.json").write_text(json.dumps({"voice_profile": "narrator", "voice_on": False, "soundbar_mode": "ai"}))
    monkeypatch.delenv("CODE_GOSSIP_INTERNAL", raising=False)
    sid = runtime.observe("codex", "UserPromptSubmit", {"session_id": "test", "prompt": "Fix"}, root=tmp_path, launch=False)
    store = Store(tmp_path / "state/trajectories.sqlite3")
    assert len(store.export(sid)["events"]) == 1
    store.close()
    monkeypatch.setenv("CODE_GOSSIP_INTERNAL", "1")
    assert runtime.observe("codex", "UserPromptSubmit", {"session_id": "internal"}, root=tmp_path) is None


def test_delivery_history_records_failure_not_success(store):
    sid = add(store, "UserPromptSubmit", prompt="Fix")
    add(store, "Stop")
    drain(store, sid, Model(narration="Tests still fail."))
    item = store.next_delivery()
    store.delivery_status(item["id"], "failed", 201)
    assert store.delivered(sid) == []
    store.delivery_status(item["id"], "completed", 202)
    assert store.delivered(sid) == ["Tests still fail."]


def test_single_worker_lock_and_idle_batch_policy(store, tmp_path):
    first = runtime.lock(tmp_path, "session-1.lock")
    assert runtime.lock(tmp_path, "session-1.lock") is None
    first.close()
    second = runtime.lock(tmp_path, "session-1.lock")
    assert second is not None
    second.close()
    sid = add(store, "UserPromptSubmit", prompt="Fix", now=100)
    processor = Processor(store, Model())
    assert processor.step(sid, 101) is None
    assert processor.step(sid, 102) == "batch"


@pytest.mark.parametrize("text", ["abc", "😀", '\\"'])
def test_large_payload_is_explicitly_truncated(text):
    event = Observation.from_hook("codex", "PostToolUse", {"session_id": "x", "tool_response": {"output": text * 100000}})
    assert json.loads(event.payload)["truncated"]
    assert len(event.payload.encode()) < 65536


def test_expiry_cascades_through_both_trajectories(store):
    sid = add(store, "UserPromptSubmit", prompt="Old", now=1)
    add(store, "Stop", now=2)
    drain(store, sid, Model(), now=3)
    store.prune(now=8 * 86400)
    assert store.session(sid) is None
    assert store.rows("SELECT * FROM interaction_records") == []
    assert store.rows("SELECT * FROM session_records") == []


def test_representative_trace_replay():
    from engine.trajectory.replay import replay
    fixture = json.loads((Path(__file__).parent / "fixtures/trajectory-session.json").read_text())
    result = replay(fixture)
    session = result["sessions"][0]
    assert len(session["interaction_records"]) == 4
    assert len(session["session_records"]) == 2
    assert len(session["narrations"]) == 4
    assert [n["status"] for n in session["narrations"]].count("silent") == 2
    assert "full test suite was not run" in session["interaction_records"][-1]["summary"]


def test_codex_quiet_result_is_collected_before_audio_filter(tmp_path):
    import codex
    payload = {"session_id": "x", "hook_event_name": "PostToolUse", "tool_name": "Read", "tool_response": {"text": "evidence"}}
    with patch("engine.trajectory.runtime.observe") as observe, patch.object(codex.subprocess, "run") as audio:
        codex.dispatch(payload, tmp_path)
    observe.assert_called_once_with("codex", "PostToolUse", payload, root=tmp_path)
    audio.assert_not_called()


def test_collection_failure_does_not_disable_claude_audio(tmp_path):
    import claude
    with patch("engine.trajectory.runtime.observe", side_effect=RuntimeError), patch.object(claude.subprocess, "run") as audio:
        claude.dispatch({"hook_event_name": "Stop", "session_id": "x"}, tmp_path)
    audio.assert_called_once()


def test_internal_provider_calls_do_not_reenter_hooks(tmp_path, monkeypatch):
    import codex
    import claude
    monkeypatch.setenv("CODE_GOSSIP_INTERNAL", "1")
    with patch("engine.trajectory.runtime.observe") as observe, patch("subprocess.run") as audio:
        codex.dispatch({"hook_event_name": "Stop"}, tmp_path)
        claude.dispatch({"hook_event_name": "Stop"}, tmp_path)
    observe.assert_not_called()
    audio.assert_not_called()


def test_worker_flushes_last_batch_without_another_hook(tmp_path, monkeypatch):
    from engine import llm
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])
    monkeypatch.setattr(runtime.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(runtime, "start", Mock())
    monkeypatch.setattr(llm, "client", lambda config: Model())
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/config.json").write_text('{"voice_on":true,"voice_profile":"narrator"}')
    store = Store(tmp_path / "state/trajectories.sqlite3")
    sid = add(store, "UserPromptSubmit", prompt="Fix", now=100)
    runtime.work(tmp_path, sid)
    assert clock[0] >= 102
    assert len(store.export(sid)["interaction_records"]) == 1
    assert len(store.export(sid)["session_records"]) == 0
    store.close()


@pytest.mark.parametrize("summary_count", [8, 13])
def test_worker_stops_new_requests_when_disabled_during_compaction(tmp_path, monkeypatch, summary_count):
    from engine import llm
    config_file = tmp_path / "configs/config.json"
    config_file.parent.mkdir()
    config_file.write_text('{"voice_on":true,"voice_profile":"narrator","soundbar_mode":"ai"}')
    monkeypatch.setattr(runtime.time, "time", lambda: 1000)
    sleep = Mock()
    monkeypatch.setattr(runtime.time, "sleep", sleep)
    monkeypatch.setattr(runtime, "start", Mock())
    model = Model()

    def generate(request):
        result = model(request)
        if len(model.requests) == 1:
            assert request.purpose == "compress"
            config_file.write_text('{"voice_on":false,"voice_profile":"narrator","soundbar_mode":"effects"}')
        return result

    monkeypatch.setattr(llm, "client", lambda config: generate)
    store = Store(tmp_path / "state/trajectories.sqlite3")
    try:
        sid = add(store, "UserPromptSubmit", turn_id="turn", prompt="Fix", now=100)
        for n in range(summary_count):
            add(store, "PostToolUse", now=100 + n * 20, turn_id="turn")
            batch = store.next_batch(sid)
            store.seal_due(sid, 120 + n * 20)
            store.commit_batch(BatchSummary(batch["id"], "Prior evidence. " * 120), 120 + n * 20)
        add(store, "PostToolUse", now=500, turn_id="turn", tool_response={"output": "new evidence"})
        pending = store.next_batch(sid)["id"]
        events = store.export(sid)["events"]
        runtime.work(tmp_path, sid)
        assert [r.purpose for r in model.requests] == ["compress"]
        assert store.next_batch(sid)["id"] == pending
        assert store.next_batch(sid)["attempts"] == 0
        assert store.next_batch(sid)["error"] == ""
        assert len(store.export(sid)["interaction_records"]) == summary_count
        sleep.assert_not_called()

        # Re-enable AI while muted: the retained batch must still be processed.
        config_file.write_text('{"voice_on":false,"voice_profile":"narrator","soundbar_mode":"ai"}')
        runtime.work(tmp_path, sid)
        assert store.next_batch(sid) is None
        assert len(store.export(sid)["interaction_records"]) == summary_count + 1
        assert store.export(sid)["events"] == events
    finally:
        store.close()


def test_raw_storage_limit_preserves_trajectory(store):
    sid = add(store, "UserPromptSubmit", prompt="Fix")
    add(store, "PostToolUse", tool_response={"output": "large log " * 1000})
    add(store, "Stop")
    drain(store, sid, Model())
    store.limit_payloads(sid, limit=1000)
    export = store.export(sid)
    assert len(export["interaction_records"]) == len(export["session_records"]) == 1
    assert any(json.loads(e["payload"]).get("evicted") for e in export["events"])


def test_cli_provider_marks_its_own_hook_origin():
    from engine import llm
    with patch.object(llm.subprocess, "run", return_value=Mock(returncode=0, stdout="summary")) as run:
        assert llm._call_claude_cli("model", "system", "user") == "summary"
    assert run.call_args.kwargs["env"]["CODE_GOSSIP_INTERNAL"] == "1"


def test_speech_acknowledges_actual_player_failure():
    from engine import speech
    import subprocess
    with patch.object(speech.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "say")):
        assert speech.speak_say("hello", "Tara", 100) is False


def test_new_interaction_supersedes_pending_speech(store):
    sid = add(store, "UserPromptSubmit", prompt="First")
    add(store, "Stop")
    drain(store, sid, Model(narration="First result"))
    item = store.next_delivery()
    assert store.delivery_current(item)
    add(store, "UserPromptSubmit", prompt="Second")
    assert not store.delivery_current(item)


def test_late_old_result_updates_memory_without_superseding_current_speech(store):
    sid = add(store, "UserPromptSubmit", turn_id="first", prompt="First")
    add(store, "Stop", turn_id="first")
    drain(store, sid, Model(narration="First result"))
    add(store, "UserPromptSubmit", turn_id="second", prompt="Second")
    add(store, "Stop", turn_id="second")
    drain(store, sid, Model(narration="Second result"))
    add(store, "PostToolUse", now=201, turn_id="first", tool_response={"output": "late result"})
    model = Model(narration="Late first result")
    drain(store, sid, model, now=204)
    assert len(store.export(sid)["interaction_records"]) == 3
    assert len(store.export(sid)["session_records"]) == 2
    assert store.next_delivery()["text"] == "Second result"
    assert not any(r.purpose == "narration" for r in model.requests)


def test_crashed_speaker_is_not_replayed(store):
    sid = add(store, "UserPromptSubmit", prompt="First")
    add(store, "Stop")
    drain(store, sid, Model(narration="First result"))
    item = store.next_delivery()
    store.delivery_status(item["id"], "playing", 200)
    store.recover_delivery(201)
    assert store.next_delivery() is None
    assert store.export(sid)["narrations"][0]["status"] == "uncertain"


def test_subagent_evidence_keeps_its_parent_interaction(store):
    sid = add(store, "UserPromptSubmit", turn_id="first", prompt="First")
    add(store, "SubagentStart", turn_id="first", agent_id="child")
    add(store, "UserPromptSubmit", turn_id="second", prompt="Second")
    add(store, "PostToolUse", agent_id="child", turn_id="child-turn", tool_response={"output": "child result"})
    export = store.export(sid)
    assert len(export["interactions"]) == 2
    assert export["events"][-1]["interaction_id"] == export["interactions"][0]["id"]


def test_live_narrator_does_not_reserve_unused_playback_budget(tmp_path):
    import shutil
    import subprocess
    source = Path(__file__).resolve().parents[1] / "code-gossip"
    for name in ("engine/play.sh", "engine/playback_gate.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/config.json").write_text('{"effects_on":false,"voice_on":true,"voice_profile":"narrator"}')
    result = subprocess.run(["bash", str(tmp_path / "engine/play.sh"), "read"], input='{"session_id":"x"}',
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert not (tmp_path / "state/playback/state.json").exists()


def test_repeated_line_stays_silent_without_losing_trajectory_records(store):
    sid = add(store, "UserPromptSubmit", prompt="Fix")
    model = Model(narration="Tests still fail.")
    drain(store, sid, model, now=103)
    item = store.next_delivery()
    store.delivery_status(item["id"], "completed", 104)
    add(store, "PostToolUse", now=105, tool_response={"output": "same failure"})
    drain(store, sid, model, now=108)
    export = store.export(sid)
    assert len(export["interaction_records"]) == 2
    assert export["narrations"][-1]["status"] == "silent"
