"""Environment health and repair must not trust a stale install flag."""
from unittest.mock import Mock

import pytest
from engine import integrations


@pytest.fixture
def integration(tmp_path, monkeypatch):
    item = integrations.VenvIntegration('kokoro', ['kokoro'], [], (3,9), (3,12), 'import kokoro', tmp_path / 'venv')
    monkeypatch.setattr(integrations, '_setup_loggers', lambda: None)
    monkeypatch.setattr(integrations, 'read_integrations', lambda: {'kokoro_installed':True})
    monkeypatch.setattr(integrations, 'write_integration', Mock())
    return item


def test_cached_flag_does_not_hide_missing_python(integration):
    assert not integration.is_installed()


def test_cached_flag_does_not_hide_broken_import(integration, monkeypatch):
    integration.venv_py.parent.mkdir(parents=True)
    integration.venv_py.touch()
    worker = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    assert not integration.is_installed()
    integrations.write_integration.assert_called_once_with('kokoro_installed', False)


def test_verified_health_cache_invalidated_by_repair_and_missing_python(integration, monkeypatch):
    integration.venv_py.parent.mkdir(parents=True)
    integration.venv_py.touch()
    worker = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    assert integration.is_installed()
    assert integration.is_installed()
    assert worker.call_count == 1
    integration._set_progress('running', 'Repairing')
    assert not integration.is_installed()
    integration._set_progress('done', 'Installed')
    assert integration.is_installed()
    assert worker.call_count == 2
    integration.venv_py.unlink()
    assert not integration.is_installed()


@pytest.mark.parametrize('uv', [False, True])
def test_repair_reinstalls_existing_packages(integration, monkeypatch, uv):
    worker = Mock(return_value=Mock(returncode=0, stdout='', stderr=''))
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    monkeypatch.setattr(integrations.shutil, 'which', lambda _: '/usr/bin/uv' if uv else None)
    assert integration.install_packages(uv, reinstall=True)
    command = worker.call_args.args[0]
    assert ('--reinstall' if uv else '--force-reinstall') in command


def test_installation_inventory_needs_files_but_never_imports(integration, monkeypatch):
    worker = Mock(side_effect=AssertionError('Inventory must not run Python'))
    monkeypatch.setattr(integrations.subprocess, 'run', worker)
    assert not integration.is_present()
    integration.venv_py.parent.mkdir(parents=True)
    integration.venv_py.touch()
    assert not integration.is_present()
    package = integration.venv_dir / 'lib/python3.11/site-packages/kokoro/__init__.py'
    package.parent.mkdir(parents=True)
    package.touch()
    assert integration.is_present()
    integration.venv_py.unlink()
    assert not integration.is_present()
    worker.assert_not_called()
