"""CLI adapter: parse a request, execute it, and print the resulting status."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .check import check_for_updates, status
from .config import UpdatePaths
from .entities import UpdateStatus
from .errors import UpdateError
from .process import start_update
from .storage import status_payload
from .update import run_update


def main(root: Path) -> int:
    args = parse_arguments()
    try:
        code = execute(root, args)
        if args.action != "_run":
            print_status(status(root), args)
        return code
    except KeyboardInterrupt:
        print("Stopped waiting. An update already started continues independently; use update.sh status to follow it.", file=sys.stderr)
        return 130
    except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check for or explicitly install a Code Gossip release.")
    parser.add_argument("action", choices=("check", "update", "status", "_run"), nargs="?", default="check")
    parser.add_argument("--json", action="store_true", help="print machine-readable status")
    parser.add_argument("--lock-fd", type=int, help=argparse.SUPPRESS)
    return parser.parse_args()


def execute(root: Path, args: argparse.Namespace) -> int:
    if args.action == "_run":
        if args.lock_fd is None:
            raise UpdateError("The worker requires an inherited update lock.")
        return run_update(root, args.lock_fd)
    if args.action == "check":
        check_for_updates(root, force=True)
    elif args.action == "update":
        worker = start_update(root)
        if worker:
            if not args.json:
                print(f"Updating Code Gossip. Progress: {UpdatePaths(root).log}", flush=True)
            return worker.wait()
    return 0


def print_status(result: UpdateStatus, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(status_payload(result)))
        return
    if result.development:
        print(f"Installed: {result.installed}")
        print("Development installation: update the checkout and rerun install.sh --dev.")
        return
    if args.action == "update" or result.running:
        message = result.message or "An update is already running."
    else:
        print("Installed: " + result.installed)
        if result.available and result.release:
            print(f"Available: {result.release.version}\n{result.release.notes_url}")
            print("Run ~/.code-gossip/update.sh update to install.")
        else:
            print("Up to date." if result.checked_at else "No update check recorded yet.")
        message = result.message if args.action == "status" else ""
    if message:
        print(message)
        if result.guidance:
            print(result.guidance)
