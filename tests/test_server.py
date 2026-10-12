"""Server API tests.

Tests server.py functions without starting the HTTP server.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOUNDBAR_DIR = REPO_ROOT / "code-gossip"

if str(SOUNDBAR_DIR) not in sys.path:
    sys.path.insert(0, str(SOUNDBAR_DIR))


class TestServerImport:
    """server.py must import without side effects."""

    def test_import_server(self):
        import server
        assert hasattr(server, "get_status")
        assert hasattr(server, "CONFIG_KEYS")


class TestVolStr:
    """_vol_str converts integer 0-100 to afplay volume string."""

    def test_zero(self):
        from server import _vol_str
        assert _vol_str(0) == "0.00"

    def test_fifty(self):
        from server import _vol_str
        assert _vol_str(50) == "0.50"

    def test_hundred(self):
        from server import _vol_str
        assert _vol_str(100) == "1.00"

    def test_seventy_five(self):
        from server import _vol_str
        assert _vol_str(75) == "0.75"

    def test_one(self):
        from server import _vol_str
        assert _vol_str(1) == "0.01"

    def test_ninety_nine(self):
        from server import _vol_str
        assert _vol_str(99) == "0.99"


class TestSpecLabel:
    """_spec_label derives display labels from sound specs."""

    def test_sox_spec(self):
        from server import _spec_label
        spec = {"sox": "synth 0.3 sine 300 fade 0.05 0.3 0.2 reverb 40"}
        label = _spec_label(spec)
        assert "synth" in label
        assert "sine" in label

    def test_file_spec(self):
        from server import _spec_label
        spec = {"file": "sounds/paper/bell.mp3"}
        label = _spec_label(spec)
        assert label == "bell.mp3"

    def test_file_spec_basename(self):
        from server import _spec_label
        spec = {"file": "/System/Library/Sounds/Glass.aiff"}
        label = _spec_label(spec)
        assert label == "Glass.aiff"

    def test_files_spec(self):
        from server import _spec_label
        spec = {"files": ["pencil1.mp3", "pencil2.mp3"]}
        label = _spec_label(spec)
        assert label == "pencil1.mp3"

    def test_sequence_spec(self):
        from server import _spec_label
        spec = {"sequence": [["book_open.mp3", "page_flip.mp3"]]}
        label = _spec_label(spec)
        assert "book_open.mp3" in label
        assert "page_flip.mp3" in label

    def test_empty_spec(self):
        from server import _spec_label
        assert _spec_label({}) == "..."


class TestSpecOrigin:
    """_spec_origin classifies sound source type."""

    def test_sox_is_generated(self):
        from server import _spec_origin
        assert _spec_origin({"sox": "synth 0.1 sine 440"}) == "generated"

    def test_system_file(self):
        from server import _spec_origin
        assert _spec_origin({"file": "/System/Library/Sounds/Glass.aiff"}) == "system"

    def test_mp3_is_sampled(self):
        from server import _spec_origin
        assert _spec_origin({"file": "bell.mp3"}) == "sampled"

    def test_aiff_is_recorded(self):
        from server import _spec_origin
        assert _spec_origin({"file": "command_center.aiff"}) == "recorded"

    def test_files_mp3(self):
        from server import _spec_origin
        assert _spec_origin({"files": ["a.mp3", "b.mp3"]}) == "sampled"

    def test_sequence_mp3(self):
        from server import _spec_origin
        assert _spec_origin({"sequence": [["a.mp3", "b.mp3"]]}) == "sampled"


class TestParseProfiles:
    """Profile parsing from manifest."""

    def test_parse_effects_profiles_returns_all(self, sounds_json):
        from server import parse_effects_profiles
        profiles = parse_effects_profiles()
        manifest_names = set(sounds_json["effects"].keys())
        assert set(profiles.keys()) == manifest_names

    def test_parse_voice_profiles_includes_expected(self):
        from server import parse_voice_profiles
        profiles = parse_voice_profiles()
        # Must include senior (TTS), narrator (LLM), and generals (manifest)
        assert "senior" in profiles
        assert "narrator" in profiles
        assert "generals" in profiles

    def test_effects_profile_events_have_cmd_and_origin(self):
        from server import parse_effects_profiles
        profiles = parse_effects_profiles()
        for prof_name, events in profiles.items():
            for event, info in events.items():
                assert "cmd" in info, f"{prof_name}/{event} missing 'cmd'"
                assert "origin" in info, f"{prof_name}/{event} missing 'origin'"


class TestGetStatus:
    """get_status() returns complete state for the UI."""

    def test_returns_required_keys(self):
        from server import get_status
        status = get_status()
        required = {
            "effects_profiles", "voice_profiles", "voice_profile_names",
            "phrases", "events", "dialogue_events", "voices",
            "tts_engines", "kokoro_voices",
            "narrator_providers", "narrator_styles", "narrator_styles_defaults",
        }
        missing = required - set(status.keys())
        assert not missing, f"get_status() missing keys: {missing}"

    def test_narrator_styles_shape(self):
        from server import get_status
        status = get_status()
        styles = status["narrator_styles"]
        assert isinstance(styles, dict) and styles
        for name, entry in styles.items():
            assert isinstance(entry, dict), f"style '{name}' not a dict"
            assert "label" in entry and "prompt" in entry, (
                f"style '{name}' missing label/prompt"
            )

    def test_events_list_covers_both_agents(self):
        from server import get_status
        status = get_status()
        assert set(status["events"]) == {
            "session_start", "session_end", "user_prompt", "edit", "read", "search",
            "bash", "tool", "plan", "test", "build", "git", "permission", "error",
            "git_status", "git_history", "git_commit", "git_push",
            "subagent_start", "subagent_stop", "pre_compact", "compact", "stop", "interrupt",
        }


class TestCodexApprovalPreference:
    def test_mixer_config_persists_preference_and_preserves_other_settings(self, tmp_path):
        import server
        config = tmp_path / 'config.json'
        config.write_text('{"voice_profile": "generals", "voice_on": true}')
        handler = Mock()
        with patch.object(server, 'CONFIG_FILE', config):
            assert server.get_status()['codex_permission_sound_on'] is True
            for enabled in (False, True):
                server.Handler._handle_post(handler, '/api/config', {'codex_permission_sound_on': enabled})
                saved = json.loads(config.read_text())
                assert saved['codex_permission_sound_on'] is enabled
                assert saved['voice_profile'] == 'generals'
                assert saved['voice_on'] is True
                assert handler.json_response.call_args.args[0]['ok'] is True
                assert server.get_status()['codex_permission_sound_on'] is enabled


class TestGetPython3:
    """get_python3() resolves a valid executable."""

    def test_returns_executable_path(self):
        from server import get_python3
        p = get_python3()
        assert os.path.isfile(p), f"get_python3() returned non-file: {p}"
        assert os.access(p, os.X_OK), f"get_python3() returned non-executable: {p}"


@pytest.fixture
def isolated_preferences(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(server, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(server, 'PHRASES_FILE', tmp_path / 'phrases.json')
    monkeypatch.setattr(server, 'STYLES_FILE', tmp_path / 'styles.json')
    monkeypatch.setattr(server, 'get_voices', lambda: [{'name': 'Tara'}, {'name': 'Aman'}, {'name': 'Samantha'}])
    config = {**server.DEFAULTS, 'effects_on': True, 'narrator_api_key': 'private-example', 'unrelated': 'preserve'}
    server.CONFIG_FILE.write_text(json.dumps(config))
    return server


def test_activation_preserves_unrelated_settings_and_saves_dialogue(isolated_preferences):
    server = isolated_preferences
    server.apply_selection({'mode': 'phrases', 'enabled': False,
                            'config': {'voice_main': 'Samantha', 'voice_sub': 'Aman'},
                            'phrases': {'subagent_start': [['Main', 'Sub']]}})
    config = server.read_config()
    assert config['voice_main'] == 'Samantha'
    assert config['voice_sub'] == 'Aman'
    assert config['soundbar_mode'] == 'phrases'
    assert not config['effects_on'] and not config['voice_on']
    assert config['unrelated'] == 'preserve'
    assert config['narrator_api_key'] == 'private-example'
    assert server.read_phrases()['subagent_start'] == [['Main', 'Sub']]
    assert server.read_phrases()['edit']


@pytest.mark.parametrize('phrases', [
    {'unknown': ['x']}, {'subagent_start': [['Only one']]},
    {'edit': ['']}, {'edit': [None]}, {'edit': [['bad', 'pair']]},
])
def test_invalid_phrase_drafts_do_not_change_files(isolated_preferences, phrases):
    server = isolated_preferences
    before = server.CONFIG_FILE.read_bytes()
    with pytest.raises(ValueError):
        server.apply_selection({'mode': 'phrases', 'enabled': True, 'config': {}, 'phrases': phrases})
    assert server.CONFIG_FILE.read_bytes() == before
    assert not server.PHRASES_FILE.exists()


def test_activation_restores_phrase_file_if_config_write_fails(isolated_preferences, monkeypatch):
    server = isolated_preferences
    server.PHRASES_FILE.write_text('{"edit": ["Keep this"]}')
    before = server.PHRASES_FILE.read_bytes()
    real_write = server.atomic_json
    def write(path, data):
        if path == server.CONFIG_FILE:
            raise OSError('disk failure')
        return real_write(path, data)
    monkeypatch.setattr(server, 'atomic_json', write)
    with pytest.raises(OSError):
        server.apply_selection({'mode': 'phrases', 'enabled': True, 'config': {}, 'phrases': {'edit': ['New']}})
    assert server.PHRASES_FILE.read_bytes() == before


def test_provider_draft_never_reuses_key_for_different_provider(isolated_preferences):
    server = isolated_preferences
    assert server.draft_config({'config': {'narrator_provider': 'openai'}})['narrator_api_key'] == ''
    assert server.read_config()['narrator_api_key'] == 'private-example'


def test_checks_send_drafts_over_stdin_without_writing(isolated_preferences):
    server = isolated_preferences
    before = server.CONFIG_FILE.read_bytes()
    with patch.object(server.subprocess, 'run', return_value=Mock(returncode=0, stdout='{"ok": true}')) as run:
        server.draft_request({'mode': 'ai', 'scope': 'provider', 'config': {'narrator_provider': 'openai', 'narrator_model': 'test-model', 'narrator_api_key': 'draft-secret'}}, check=True)
    args, kwargs = run.call_args
    assert args[0][0] == server.get_python3()
    assert 'draft-secret' not in str(args)
    request = json.loads(kwargs['input'])
    assert request['check'] is True
    assert request['config']['narrator_api_key'] == 'draft-secret'
    assert request['config']['narrator_model'] == 'test-model'
    assert server.CONFIG_FILE.read_bytes() == before


def test_effect_preview_uses_unsaved_pack(isolated_preferences):
    server = isolated_preferences
    before = server.CONFIG_FILE.read_bytes()
    with patch.object(server, 'setup_status', return_value={'effects': {'paper': {'ready': True}}}), patch.object(server, 'play_profile_event') as play:
        server.draft_request({'mode': 'effects', 'config': {'effects_profile': 'paper'}})
    assert play.call_args.args[:3] == ('effects', 'paper', 'edit')
    assert play.call_args.args[3]['effects_profile'] == 'paper'
    assert server.CONFIG_FILE.read_bytes() == before


def test_setup_discovers_sox_from_manifest(isolated_preferences):
    server = isolated_preferences
    with patch.object(server, 'executable', side_effect=lambda name: None if name == 'play' else '/usr/bin/'+name), patch.object(server.kokoro, 'is_present', return_value=False):
        status = server.setup_status()
    assert status['effects']['sci-fi']['sox']
    assert not status['effects']['sci-fi']['ready']
    assert not status['effects']['paper']['sox']
    assert not status['kokoro']


def test_preview_event_and_alternative_are_explicit(isolated_preferences):
    server = isolated_preferences
    with patch.object(server, 'setup_status', return_value={'clips': {'generals': {'ready': True}}}), patch.object(server, 'play_profile_event') as play:
        server.draft_request({'mode':'clips','event':'subagent_start','variant':2,'config':{}})
        assert play.call_args.args[:3] == ('voice','generals','subagent_start')
        assert play.call_args.kwargs == {'variant':2,'wait':True}
        with pytest.raises(ValueError):
            server.draft_request({'mode':'clips','event':'subagent_start','variant':999,'config':{}})


def test_install_progress_is_read_without_python_installation(isolated_preferences):
    server = isolated_preferences
    with patch.object(server.kokoro, '_progress', {'status':'running','message':'Installing packages'}), patch.object(server.kokoro, 'is_present', return_value=False), patch.object(server.kokoro, 'find_python') as find:
        status = server.setup_status()
        assert status['installing']
        assert status['installMessage'] == 'Installing packages'
        find.assert_not_called()


def test_preview_waits_for_audio_and_uses_selected_clip(isolated_preferences):
    server = isolated_preferences
    with patch.object(server.subprocess, 'run') as run, patch.object(server.subprocess, 'Popen') as background:
        server.play_profile_event('voice','generals','subagent_start',variant=1,wait=True)
        command = run.call_args.args[0]
        assert 'cmd_move_out.aiff' in command[-1]
        assert 'unit_on_my_way.aiff' in command[-1]
        assert run.call_args.kwargs['check']
        background.assert_not_called()


def test_live_models_use_only_selected_provider_credentials(isolated_preferences):
    server = isolated_preferences
    before = server.CONFIG_FILE.read_bytes()
    with patch.object(server, 'list_models', return_value={'ok': True, 'models': []}) as discover:
        server.narrator_models({'config': {}})
        discover.assert_called_with('claude_cli', 'private-example')
        server.narrator_models({'config': {'narrator_provider': 'openai'}})
        discover.assert_called_with('openai', '')
        server.narrator_models({'config': {'narrator_provider': 'openai', 'narrator_api_key': 'draft-secret'}})
        discover.assert_called_with('openai', 'draft-secret')
    assert server.CONFIG_FILE.read_bytes() == before
    assert all('models' not in provider for provider in server.NARRATOR_PROVIDERS.values())


@pytest.mark.parametrize('changes', [{'narrator_provider': 'unknown'}, {'narrator_api_key': 42}, {'tts_engine': 'kokoro'}, []])
def test_live_models_reject_invalid_config(isolated_preferences, changes):
    with pytest.raises(ValueError):
        isolated_preferences.narrator_models({'config': changes})


def test_provider_check_ignores_unavailable_speech(isolated_preferences):
    server = isolated_preferences
    with patch.object(server, 'get_voices', return_value=[]), patch.object(server.subprocess, 'run', return_value=Mock(returncode=0, stdout='{"ok":true}')) as worker:
        assert server.draft_request({'mode':'ai','scope':'provider','config':{'tts_engine':'say','voice_main':'Missing voice'}}, check=True)['ok']
        assert json.loads(worker.call_args.kwargs['input'])['scope'] == 'provider'


def test_speech_check_ignores_invalid_provider_draft(isolated_preferences):
    server = isolated_preferences
    with patch.object(server.subprocess, 'run', return_value=Mock(returncode=0, stdout='{"ok":true}')) as worker:
        assert server.draft_request({'mode':'ai','scope':'speech','config':{'narrator_provider':'unavailable','narrator_style':'removed-style'}}, check=True)['ok']
        assert json.loads(worker.call_args.kwargs['input'])['scope'] == 'speech'


def test_repair_installation_bypasses_cached_install_and_starts_once(isolated_preferences, monkeypatch):
    server = isolated_preferences
    monkeypatch.setattr(server, 'stopping', False)
    monkeypatch.setattr(server.kokoro, '_progress', {'status':'idle','message':''})
    handler = object.__new__(server.Handler)
    handler.json_response = Mock()
    with patch.object(server.kokoro, 'is_installed', return_value=True) as installed, patch.object(server.threading, 'Thread') as thread:
        handler._handle_post('/api/kokoro-install', {'repair':True})
        handler._handle_post('/api/kokoro-install', {'repair':True})
        installed.assert_not_called()
        thread.assert_called_once_with(target=server.kokoro.install, daemon=False)
        thread.return_value.start.assert_called_once()
        assert server.kokoro.progress['status'] == 'running'


def test_slow_check_does_not_block_controls_or_status(isolated_preferences, monkeypatch):
    import threading
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    server = isolated_preferences
    entered, release = threading.Event(), threading.Event()
    def slow_check(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return {'ok':True}
    monkeypatch.setattr(server, 'draft_request', slow_check)
    http = server.ReuseHTTPServer(('127.0.0.1', 0), server.Handler)
    serving = threading.Thread(target=http.serve_forever)
    serving.start()
    base = f'http://127.0.0.1:{http.server_port}'
    def request(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.load(response)
    try:
        with ThreadPoolExecutor() as pool:
            checking = pool.submit(request, '/api/draft-check', {'mode':'ai'})
            try:
                assert entered.wait(2)
                assert request('/api/health')['app'] == 'code-gossip'
                assert request('/api/config', {'effects_on':False})['ok']
                assert server.read_config()['effects_on'] is False
            finally:
                release.set()
            assert checking.result()['ok']
    finally:
        release.set()
        http.shutdown()
        http.server_close()
        serving.join()


def test_shutdown_rejected_while_installing(isolated_preferences, monkeypatch):
    server = isolated_preferences
    monkeypatch.setattr(server, 'stopping', False)
    monkeypatch.setattr(server.kokoro, '_progress', {'status':'running','message':'Installing packages'})
    handler = object.__new__(server.Handler)
    handler.path = '/api/shutdown'
    handler.server = Mock(server_port=8111)
    handler.headers = {'Origin':'http://localhost:8111','X-Soundbar-Request':'ui'}
    handler.json_response = Mock()
    handler.do_POST()
    result = handler.json_response.call_args.args[0]
    assert not result['ok']
    assert 'Installation is in progress' in result['error']
    assert not server.stopping
    handler.server.shutdown.assert_not_called()


def test_initial_status_never_imports_kokoro(isolated_preferences):
    server = isolated_preferences
    with patch.object(server.kokoro, 'is_installed', side_effect=AssertionError('Expensive import during page load')), patch.object(server.kokoro, 'is_present', return_value=True):
        assert server.get_status()['setup']['kokoro'] is True
        assert server.setup_status()['kokoro'] is True
