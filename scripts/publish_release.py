"""Publish the tested package through gh; reruns never replace different bytes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code-gossip'))
from updates.constants import REPOSITORY, PACKAGE_ASSET
from updates.entities import Version


def lookup(path):
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/releases/{path}'],
                            capture_output=True, text=True)
    if result.returncode:
        if '(HTTP 404)' in result.stderr:
            return None
        raise RuntimeError('GitHub release lookup failed: ' + result.stderr)
    return json.loads(result.stdout)


def gh(*args):
    subprocess.run(['gh', 'release', *args, '--repo', REPOSITORY], check=True)


def publish(tag, package):
    version = Version.parse(tag)
    package = Path(package)
    if package.name != PACKAGE_ASSET or not package.is_file():
        raise ValueError('The tested code-gossip.zip package is required.')
    with zipfile.ZipFile(package) as archive:
        packaged = archive.read('release/code-gossip/VERSION').decode().strip()
    if Version.parse(packaged) != version:
        raise ValueError('The installer version does not match the release tag.')
    release = lookup('tags/' + tag)
    if release and release.get('prerelease'):
        raise ValueError('A stable version tag cannot publish a prerelease.')
    if release is None or release.get('draft'):
        latest = lookup('latest')
        latest_flag = '--latest' if not latest or version > Version.parse(latest['tag_name']) else '--latest=false'
    if release is None:
        gh('create', tag, str(package), '--verify-tag', '--title', tag, '--generate-notes', '--draft')
        gh('edit', tag, '--draft=false', latest_flag)
        return
    assets = [a for a in release.get('assets', []) if a['name'] == PACKAGE_ASSET]
    if assets:
        if len(assets) != 1 or assets[0]['state'] != 'uploaded':
            raise ValueError('An incomplete installation asset already exists.')
        with tempfile.TemporaryDirectory() as temporary:
            gh('download', tag, '--pattern', PACKAGE_ASSET, '--dir', temporary)
            if (Path(temporary) / PACKAGE_ASSET).read_bytes() != package.read_bytes():
                raise ValueError('The published installer differs from the tested package.')
    else:
        gh('upload', tag, str(package))
    if release.get('draft'):
        gh('edit', tag, '--draft=false', latest_flag)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    publish(args.tag, args.package)
