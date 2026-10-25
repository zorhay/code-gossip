"""Panel readiness, reuse, startup cleanup, and installer launch policy."""
import argparse
from pathlib import Path
import socket
import subprocess
from unittest.mock import Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
import installer
import launcher


@pytest.mark.parametrize('no_panel,dry_run,expected', [(False, False, True), (True, False, False), (False, True, False)])
def test_install_opens_panel_only_after_success(tmp_path, monkeypatch, no_panel, dry_run, expected):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(installer, 'install_files', Mock())
    monkeypatch.setattr(installer, 'write_hooks', Mock())
    monkeypatch.setattr(installer, 'open_panel', opened := Mock())
    args = argparse.Namespace(action='install', agents=['codex'], all=False, dev=False,
                              dry_run=dry_run, purge=False, no_panel=no_panel)
    installer.run(args)
    assert opened.called is expected
    if expected:
        opened.assert_called_once_with(tmp_path / '.code-gossip')
        installer.write_hooks.assert_called_once()


def test_failed_install_does_not_open_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(installer, 'install_files', Mock(side_effect=OSError('disk full')))
    monkeypatch.setattr(installer, 'open_panel', opened := Mock())
    args = argparse.Namespace(action='install', agents=['codex'], all=False, dev=False,
                              dry_run=False, purge=False, no_panel=False)
    with pytest.raises(OSError):
        installer.run(args)
    opened.assert_not_called()


def test_browser_failure_does_not_undo_install(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(installer.subprocess, 'run', Mock(side_effect=subprocess.TimeoutExpired('launcher', 30)))
    installer.open_panel(tmp_path)
    assert 'Installation succeeded' in capsys.readouterr().err


def test_launch_reuses_ready_server(monkeypatch):
    monkeypatch.setattr(launcher, 'ready', Mock(return_value=True))
    monkeypatch.setattr(launcher, 'open_browser', opened := Mock())
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawned := Mock())
    launcher.launch(background=True)
    opened.assert_called_once()
    spawned.assert_not_called()


def test_startup_failure_never_opens_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'ready', Mock(return_value=False))
    monkeypatch.setattr(launcher, 'open_browser', opened := Mock())
    monkeypatch.setattr(launcher.subprocess, 'Popen', Mock(return_value=Mock(poll=Mock(return_value=1))))
    with pytest.raises(RuntimeError, match='exited'):
        launcher.launch(background=True)
    opened.assert_not_called()


def test_startup_timeout_cleans_up_child(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'ready', Mock(return_value=False))
    monkeypatch.setattr(launcher.time, 'monotonic', Mock(side_effect=[0, 11]))
    monkeypatch.setattr(launcher, 'open_browser', opened := Mock())
    child = Mock(poll=Mock(return_value=None))
    monkeypatch.setattr(launcher.subprocess, 'Popen', Mock(return_value=child))
    with pytest.raises(RuntimeError, match='did not become ready'):
        launcher.launch(background=True)
    child.terminate.assert_called_once()
    opened.assert_not_called()


def test_installed_panel_ready_assets_and_reuse(tmp_path, repo_root, monkeypatch):
    """Run an isolated, real server; opening only happens once its health endpoint works."""
    import shutil
    root = tmp_path / 'runtime'
    shutil.copytree(repo_root / 'code-gossip', root,
                    ignore=shutil.ignore_patterns('state', 'version_state', '__pycache__', 'config.json', 'phrases.json', 'narrator_styles.json'))
    monkeypatch.setattr(launcher, 'ROOT', root)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv('PORT', str(port))
    urls = []
    def opened(url):
        assert launcher.ready(url)
        urls.append(url)
    monkeypatch.setattr(launcher, 'open_browser', opened)
    real_popen = subprocess.Popen
    children = []
    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    try:
        launcher.launch(background=True)
        launcher.launch(background=True)
        assert len(children) == 1
        assert len(urls) == 2
        assert children[0].poll() is None
        for path, content_type in [('/', 'text/html'), ('/ui.js', 'text/javascript')]:
            with urlopen(urls[0] + path) as response:
                assert response.headers['Content-Type'] == content_type
                assert response.read()
        monkeypatch.setattr(launcher, 'ROOT', tmp_path / 'other')
        with pytest.raises(ValueError, match='another service or Code Gossip'):
            launcher.ready(urls[0])
        monkeypatch.setattr(launcher, 'ROOT', root)
        for headers in ({}, {'Origin': 'https://example.com', 'X-Soundbar-Request': 'ui'}, {'Origin': urls[0]}):
            with pytest.raises(HTTPError) as denied:
                urlopen(Request(urls[0] + '/api/shutdown', method='POST', headers=headers))
            assert denied.value.code == 403
            assert launcher.ready(urls[0])
        request = Request(urls[0] + '/api/shutdown', method='POST',
                          headers={'Origin': urls[0], 'X-Soundbar-Request': 'ui'})
        with urlopen(request) as response:
            assert response.status == 200
        assert children[0].wait(timeout=5) == 0
        assert not (root / 'state/.server.pid').exists()
        assert not launcher.ready(urls[0])
    finally:
        for child in children:
            child.terminate()
            child.wait(timeout=5)
