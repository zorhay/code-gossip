"""Environment health and repair must not trust a stale install flag."""
from unittest.mock import Mock
import subprocess
import sys
import threading
import time

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
    monkeypatch.setattr(integration, '_run_install', worker)
    monkeypatch.setattr(integrations.subprocess, 'run', Mock())
    monkeypatch.setattr(integrations.shutil, 'which', lambda _: '/usr/bin/uv' if uv else None)
    assert integration.install_packages(uv, reinstall=True)
    command = worker.call_args.args[0]
    assert ('--reinstall' if uv else '--force-reinstall') in command


def test_install_output_is_visible_before_process_finishes(integration):
    integration._set_progress('running', 'Installing packages')
    results = []
    worker = threading.Thread(target=lambda: results.append(integration._run_install([
        sys.executable, '-u', '-c',
        "import time; print('Downloading torch (138.6 MB)', flush=True); time.sleep(2)",
    ])))
    worker.start()
    try:
        deadline = time.monotonic() + 1.5
        while not integration.progress['output'] and time.monotonic() < deadline:
            time.sleep(.01)
        assert integration.progress['output'] == ['Downloading torch (138.6 MB)']
        assert worker.is_alive()
        assert integration.progress['timeout'] == 1200
    finally:
        worker.join(5)
    assert results[0].returncode == 0


def test_install_output_is_bounded_redacted_and_retained_after_failure(integration):
    integration._set_progress('running', 'Installing packages')
    result = integration._run_install([sys.executable, '-c',
        "for n in range(20): print('Collecting package', n)\n"
        "print('ERROR https://user:secret@example.com/pkg?token=private')\nraise SystemExit(1)"])
    integration._set_progress('error', 'Package installation failed')
    progress = integration.progress
    assert result.returncode == 1
    assert len(progress['output']) == 8
    assert progress['output'][-1] == 'ERROR [download source]'
    assert 'secret' not in result.stderr
    elapsed = progress['elapsed']
    assert integration.progress['elapsed'] == elapsed
    integration._set_progress('running', 'Retrying')
    assert integration.progress['output'] == []
    assert integration.progress['elapsed'] == 0


def test_silent_install_process_obeys_remaining_twenty_minute_budget(integration, monkeypatch):
    integration._set_progress('running', 'Installing packages')
    integration._started = time.monotonic() - 1199.9
    popen = integrations.subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(integrations.subprocess, 'Popen', launch)
    with pytest.raises(subprocess.TimeoutExpired):
        integration._run_install([sys.executable, '-c', 'import time; time.sleep(30)'])
    assert processes[0].poll() is not None


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
