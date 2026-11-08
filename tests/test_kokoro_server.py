"""Model preparation and progress without downloads, torch, or personal settings."""
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import kokoro_server as daemon
import narrate


def finish(manager):
    # All workers in these tests have bounded, in-memory work.
    for _ in range(200):
        if not manager.loading:
            return
        threading.Event().wait(.01)
    pytest.fail('Model preparation did not finish')


def test_health_is_responsive_during_download_and_waits_for_voices(monkeypatch):
    manager = daemon.ModelManager()
    started, release = threading.Event(), threading.Event()

    def load():
        manager._stage('downloading', 'Downloading model', completed=0,
                       total=1000, transferred=350)
        started.set()
        assert release.wait(3)
        return object()

    monkeypatch.setattr(manager, '_load_model', load)
    voice_loader = Mock()
    monkeypatch.setattr(manager, '_load_voice', voice_loader)
    try:
        assert not manager.prepare(['af_heart'])['ready']
        assert started.wait(1)
        # A second preparation request joins the same worker.
        status = manager.prepare(['am_adam'])
        assert not status['ready']
        assert status['completed'] == 0
        assert status['transferred'] == 350
        voice_loader.assert_not_called()
    finally:
        release.set()
        finish(manager)
    assert manager.status(['af_heart', 'am_adam'])['ready']
    assert {call.args[0] for call in voice_loader.call_args_list} == {'af_heart', 'am_adam'}
    assert not manager.status(['bf_emma'])['ready']


def test_download_failure_is_sticky_until_explicit_retry(monkeypatch):
    manager = daemon.ModelManager()
    loader = Mock(side_effect=RuntimeError('https://example.test/signed?token=secret'))
    monkeypatch.setattr(manager, '_load_model', loader)
    manager.prepare(['af_heart'])
    finish(manager)
    status = manager.prepare(['af_heart'])
    assert status['state'] == 'error'
    assert not status['ready']
    assert 'secret' not in str(status)
    assert 'retry' in status['message']
    assert loader.call_count == 1
    loader.side_effect = None
    loader.return_value = object()
    monkeypatch.setattr(manager, '_load_voice', Mock())
    manager.prepare(['af_heart'], retry=True)
    finish(manager)
    assert manager.status(['af_heart'])['ready']
    assert loader.call_count == 2


def test_voice_failure_does_not_discard_ready_voices(monkeypatch):
    manager = daemon.ModelManager()
    manager.weights = object()
    manager.voices.add('af_heart')
    loader = Mock(side_effect=RuntimeError('offline'))
    monkeypatch.setattr(manager, '_load_voice', loader)
    manager.prepare(['bf_emma'])
    finish(manager)
    assert manager.status(['af_heart'])['ready']
    assert not manager.status(['bf_emma'])['ready']
    assert manager.status(['bf_emma'])['state'] == 'error'


def test_speak_returns_loading_without_waiting_for_inference(monkeypatch):
    manager = daemon.ModelManager()
    manager.loading = True
    manager.progress = {'state': 'downloading', 'message': 'Downloading model'}
    monkeypatch.setattr(daemon, 'model', manager)
    handler = object.__new__(daemon.Handler)
    with daemon.inference_lock:
        # This would deadlock if an unready request joined the speech queue.
        result = handler._speak({'text': 'Hello', 'voice': 'af_heart'})
    assert result['ok'] is False
    assert result['error'] == 'Downloading model'


def test_progress_reports_buffered_transfer_and_unknown_total(monkeypatch):
    class QuietTqdm:
        def __init__(self, *args, total=None, initial=0, **kwargs):
            self.total, self.n = total, initial

    monkeypatch.setitem(sys.modules, 'tqdm', SimpleNamespace(tqdm=QuietTqdm))
    report = Mock()
    progress = daemon.download_progress(report)(total=1000)
    progress.update_transfer(400)
    progress.set_transfer_postfix_str('200 B/s', refresh=False)
    assert report.call_args.kwargs == {'completed': 0, 'total': 1000, 'transferred': 400}
    progress.update(250)
    assert report.call_args.kwargs == {'completed': 250, 'total': 1000, 'transferred': 400}
    progress.total = None
    progress.refresh()
    assert report.call_args.kwargs['total'] is None


def test_cached_download_needs_no_fake_progress(monkeypatch):
    manager = daemon.ModelManager()
    download = Mock(return_value='/cache/voices/af_heart.pt')
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(hf_hub_download=download))
    monkeypatch.setattr(daemon, 'download_progress', lambda report: 'progress adapter')
    assert manager._download('voices/af_heart.pt') == '/cache/voices/af_heart.pt'
    assert manager.progress['completed'] == 0
    assert manager.progress['total'] is None
    assert download.call_args.kwargs['tqdm_class'] == 'progress adapter'


def test_voice_download_does_not_block_already_ready_speech(monkeypatch):
    manager = daemon.ModelManager()
    manager.weights = object()

    def download(filename):
        assert daemon.inference_lock.acquire(blocking=False)
        daemon.inference_lock.release()
        return '/cache/' + filename

    monkeypatch.setattr(manager, '_download', download)
    pipeline = SimpleNamespace(voices={}, load_voice=Mock(return_value='voice tensor'))
    constructor = Mock(return_value=pipeline)
    monkeypatch.setitem(sys.modules, 'kokoro', SimpleNamespace(KPipeline=constructor))
    manager._load_voice('bf_emma')
    assert constructor.call_args.kwargs['model'] is manager.weights
    pipeline.load_voice.assert_called_once_with('/cache/voices/bf_emma.pt')
    assert pipeline.voices['bf_emma'] == 'voice tensor'


@pytest.mark.parametrize('state,ready,pending', [('downloading',False,True), ('loading',False,True),
                                              ('error',False,False), ('ready',True,False)])
def test_check_never_confuses_daemon_health_with_readiness(monkeypatch, tmp_path, state, ready, pending):
    python = tmp_path / 'python'
    python.touch()
    sock = tmp_path / 'kokoro.sock'
    sock.touch()
    monkeypatch.setattr(narrate, 'KOKORO_VENV', python)
    monkeypatch.setattr(narrate, 'KOKORO_SOCK', sock)
    monkeypatch.setattr(narrate, '_ensure_kokoro_daemon', lambda: True)
    send = Mock(return_value={'ok':True, 'ready':ready, 'state':state, 'message':'Model status',
                              'completed':100, 'total':200, 'transferred':125})
    monkeypatch.setattr(narrate, '_kokoro_request', send)
    result = narrate.check_kokoro(['bf_emma'], prepare=True, retry=True)
    assert result['ok'] == ready
    assert result['pending'] == pending
    assert result['model']['transferred'] == 125
    send.assert_called_once_with('prepare', timeout=3, voices=['bf_emma'], retry=True)


def test_installed_packages_without_daemon_are_not_ready(monkeypatch, tmp_path):
    python = tmp_path / 'python'
    python.touch()
    monkeypatch.setattr(narrate, 'KOKORO_VENV', python)
    monkeypatch.setattr(narrate, 'KOKORO_SOCK', tmp_path / 'missing.sock')
    assert not narrate.check_kokoro()['ok']
