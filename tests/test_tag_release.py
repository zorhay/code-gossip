"""Tag validation and real publication decisions, with no GitHub writes."""
import json
from pathlib import Path
import subprocess
import zipfile

import pytest
from scripts import release_metadata, publish_release
from updates.errors import UpdateError


def package_file(tmp_path, version='1.2.3'):
    package = tmp_path / 'code-gossip.zip'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('release/code-gossip/VERSION', version + '\n')
    return package


@pytest.mark.parametrize('tag', ['0.14.0', 'v1.2.3', '10.20.30'])
def test_valid_tag_matches_checkout(monkeypatch, tag):
    calls = []
    def git(command, **kwargs):
        calls.append(command)
        return 'abc123\n'
    monkeypatch.setattr(subprocess, 'check_output', git)
    assert release_metadata.metadata('push', 'tag', tag) == (tag, 'abc123')
    assert calls[-1][-1] == f'refs/tags/{tag}^{{commit}}'


@pytest.mark.parametrize('tag', ['01.2.3', '1.02.3', '1.2.03', '1.2', '1.2.3.4',
    'v', 'v1.2.3-rc.1', '1.2.3+build', '1.2.3\n', '1.2٣.4', '1.2.3;echo bad'])
def test_invalid_versions_stop_before_tag_lookup(monkeypatch, tag):
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: 'head\n')
    with pytest.raises(UpdateError):
        release_metadata.metadata('push', 'tag', tag)


def test_branch_push_cannot_publish(monkeypatch):
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: 'head\n')
    with pytest.raises(ValueError, match='version-tag'):
        release_metadata.metadata('push', 'branch', 'main')
    assert release_metadata.metadata('pull_request', 'branch', '29/merge') == ('1.2.3', 'head')


def test_tag_must_point_to_checkout(monkeypatch):
    results = iter(['head\n', 'other\n'])
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: next(results))
    with pytest.raises(ValueError, match='checked-out'):
        release_metadata.metadata('push', 'tag', '1.2.3')


@pytest.mark.parametrize('existing,latest,asset,expected,error', [
    (None, None, None, ['create', 'edit'], None),
    (None, '1.0.0', None, ['create', 'edit'], None),
    (None, '2.0.0', None, ['create', 'edit'], None),
    ({}, None, None, ['upload'], None),
    ({}, None, 'identical', ['download'], None),
    ({}, None, 'different', ['download'], 'differs'),
    ({'draft': True}, '1.0.0', None, ['upload', 'edit'], None),
    ({'prerelease': True}, None, None, [], 'prerelease'),
])
def test_publication_and_safe_reruns(tmp_path, monkeypatch, existing, latest, asset, expected, error):
    package = package_file(tmp_path)
    release = None if existing is None else {**existing, 'assets': [
        {'name': 'code-gossip.zip', 'state': 'uploaded'}] if asset else []}
    monkeypatch.setattr(publish_release, 'lookup', lambda path:
        release if path.startswith('tags/') else {'tag_name': latest} if latest else None)
    calls = []
    def gh(*args):
        calls.append(args)
        if args[0] == 'download':
            (Path(args[args.index('--dir') + 1]) / package.name).write_bytes(package.read_bytes() if asset == 'identical' else b'different')
    monkeypatch.setattr(publish_release, 'gh', gh)
    if error:
        with pytest.raises(ValueError, match=error):
            publish_release.publish('1.2.3', package)
    else:
        publish_release.publish('1.2.3', package)
    assert [call[0] for call in calls] == expected
    if existing is None:
        assert '--verify-tag' in calls[0] and str(package) in calls[0]
        assert '--draft' in calls[0]
        assert ('--latest=false' in calls[-1]) == (latest == '2.0.0')


@pytest.mark.parametrize('code', [403, 404, 500])
def test_lookup_only_treats_404_as_missing(monkeypatch, code):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k:
        subprocess.CompletedProcess(a, 1, '', f'API failed (HTTP {code})'))
    if code == 404:
        assert publish_release.lookup('tags/1.2.3') is None
    else:
        with pytest.raises(RuntimeError, match='lookup failed'):
            publish_release.lookup('tags/1.2.3')


@pytest.mark.parametrize('existing', [None, {'draft': True}])
def test_upload_failure_cannot_publish_draft(tmp_path, monkeypatch, existing):
    package = package_file(tmp_path)
    monkeypatch.setattr(publish_release, 'lookup', lambda path: existing if path.startswith('tags/') else None)
    calls = []
    def fail(*args):
        calls.append(args[0])
        raise subprocess.CalledProcessError(1, 'gh')
    monkeypatch.setattr(publish_release, 'gh', fail)
    with pytest.raises(subprocess.CalledProcessError):
        publish_release.publish('1.2.3', package)
    assert calls == ['create' if existing is None else 'upload']


def test_package_version_mismatch_never_calls_github(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_release, 'lookup', lambda *a: pytest.fail('No GitHub call expected'))
    with pytest.raises(ValueError, match='installer version'):
        publish_release.publish('1.2.3', package_file(tmp_path, '1.2.2'))


@pytest.mark.parametrize('annotated', [False, True])
def test_real_git_version_tags(tmp_path, monkeypatch, annotated):
    monkeypatch.chdir(tmp_path)
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args], text=True).strip()
    git('init', '-q')
    git('commit', '--allow-empty', '-qm', 'release fixture')
    git('tag', *(['-a', '-m', 'release'] if annotated else []), 'v1.2.3')
    assert release_metadata.metadata('push', 'tag', 'v1.2.3') == ('v1.2.3', git('rev-parse', 'HEAD'))
    git('commit', '--allow-empty', '-qm', 'another commit')
    with pytest.raises(ValueError, match='checked-out'):
        release_metadata.metadata('push', 'tag', 'v1.2.3')
