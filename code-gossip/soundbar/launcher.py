#!/usr/bin/env python3
"""Start or reuse Soundbar, then open its ready UI in the default browser."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import ROOT


def ready(url):
    try:
        # Loopback traffic should never go through a configured HTTP proxy.
        with build_opener(ProxyHandler({})).open(url + '/api/health', timeout=0.3) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise ValueError('The port is occupied by another service.') from exc
    except (URLError, TimeoutError, OSError):
        return False
    except ValueError as exc:
        raise ValueError('The port did not return a Soundbar health response.') from exc
    if not isinstance(data, dict) or data.get('app') != 'code-gossip' or data.get('root') != str(ROOT):
        raise ValueError('The port is occupied by another service or Code Gossip installation.')
    return True


def open_browser(url):
    try:
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/open', url], check=True, timeout=10)
        elif not webbrowser.open(url):
            raise OSError('No default browser found')
    except (OSError, subprocess.SubprocessError) as exc:
        print(f'Could not open the browser ({exc}). Open {url} manually.', file=sys.stderr)


def launch(background=False):
    port = int(os.environ.get('PORT', '8111'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    url = f'http://localhost:{port}'
    if ready(url):
        print(f'Soundbar is already running: {url}')
        open_browser(url)
        return
    state = ROOT / 'state'
    state.mkdir(parents=True, exist_ok=True)
    log_path = state / 'panel.log'
    with log_path.open('a') as log:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / 'soundbar/server.py')],
            cwd=ROOT, start_new_session=background,
            stdin=subprocess.DEVNULL if background else None,
            stdout=log if background else None, stderr=log if background else None,
        )
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                raise RuntimeError(f'Soundbar exited during startup. See {log_path}.')
            if ready(url):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Soundbar did not become ready. See {log_path}.')
            time.sleep(0.1)
        print(f'Soundbar: {url}')
        open_browser(url)
        if not background:
            print('Press Ctrl+C to stop.')
            process.wait()
    finally:
        # A failed startup must not leave an orphan. Successful background runs stay alive.
        if process.poll() is None and (not background or sys.exc_info()[0] is not None):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--background', action='store_true', help='leave the server running after opening the browser')
    args = parser.parse_args()
    try:
        launch(args.background)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Soundbar: {exc}\n')


if __name__ == '__main__':
    main()
