"""Kokoro setup must discover supported interpreters before installing packages."""
from unittest.mock import Mock

import pytest
from engine import integrations


@pytest.fixture
def kokoro(monkeypatch):
    monkeypatch.setattr(integrations, '_setup_loggers', lambda: None)
    monkeypatch.setattr(integrations, 'read_integrations', lambda: {})
    monkeypatch.setattr(integrations, 'write_integration', Mock())
    monkeypatch.setattr(integrations.shutil, 'which', lambda _: None)
    return integrations.kokoro


@pytest.mark.parametrize('minor', [10, 11, 12])
def test_discovers_supported_python_in_path(kokoro, monkeypatch, minor):
    python = f'/tools/python3.{minor}'
    monkeypatch.setattr(integrations.shutil, 'which',
                        lambda name: python if name == f'python3.{minor}' else None)
    monkeypatch.setattr(integrations, '_get_python_version', lambda _: (3, minor))
    result = kokoro.find_python()
    assert result['ok']
    assert result['python'] == python
    assert result['version'] == f'3.{minor}'


def test_discovers_pyenv_python312_when_default_is313(kokoro, monkeypatch, tmp_path):
    python = tmp_path / 'versions/3.12.8/bin/python3'
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(integrations.shutil, 'which',
                        lambda name: '/tools/pyenv' if name == 'pyenv' else None)
    worker = Mock(side_effect=[
        Mock(returncode=0, stdout='3.13.7\n3.12.8\n'),
        Mock(returncode=0, stdout=str(tmp_path)),
    ])
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    result = kokoro.find_python()
    assert result['ok']
    assert result['python'] == str(python)
    assert result['method'] == 'pyenv'
    assert result['version'] == '3.12.8'


@pytest.mark.parametrize('minor, supported', [(9, False), (12, True), (13, False)])
def test_revalidates_cached_python_version(kokoro, monkeypatch, tmp_path, minor, supported):
    python = tmp_path / 'python'
    python.touch(mode=0o755)
    cached = {'ok': True, 'python': str(python), 'version': f'3.{minor}', 'method': 'direct'}
    monkeypatch.setattr(integrations, 'read_integrations', lambda: {'kokoro_python': cached})
    monkeypatch.setattr(integrations, '_get_python_version', lambda _: (3, minor))
    result = kokoro.find_python()
    assert result['ok'] is supported
    if supported:
        assert result == cached
    else:
        assert 'Python (3.10-3.12)' in result['message']
        assert 'brew install python@3.12' in result['message']


def test_uv_requests_python312(kokoro, monkeypatch, tmp_path):
    python = str(tmp_path / 'python')
    monkeypatch.setattr(integrations.shutil, 'which',
                        lambda name: '/tools/uv' if name == 'uv' else None)
    monkeypatch.setattr(integrations, '_get_python_version', lambda _: (3, 12))
    worker = Mock(return_value=Mock(returncode=0, stdout=python, stderr=''))
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    result = kokoro.find_python()
    assert result['ok']
    assert result['version'] == '3.12'
    assert [call.args[0] for call in worker.call_args_list] == [
        ['/tools/uv', 'python', 'install', '3.12'],
        ['/tools/uv', 'python', 'find', '3.12'],
    ]
