"""Validate a version-tag push before any release artifacts are built."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code-gossip'))
from updates.entities import Version


def metadata(event, ref_type, ref_name):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if event == 'pull_request':
        return '1.2.3', commit
    if event != 'push' or ref_type != 'tag':
        raise ValueError('Releases require a version-tag push.')
    Version.parse(ref_name)
    tagged = subprocess.check_output(
        ['git', 'rev-parse', '--verify', f'refs/tags/{ref_name}^{{commit}}'], text=True).strip()
    if tagged != commit:
        raise ValueError('The version tag does not match the checked-out commit.')
    return ref_name, commit


if __name__ == '__main__':
    tag, commit = metadata(os.environ['GITHUB_EVENT_NAME'], os.environ.get('GITHUB_REF_TYPE'),
                           os.environ.get('GITHUB_REF_NAME'))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'tag={tag}\ncommit={commit}\n')
