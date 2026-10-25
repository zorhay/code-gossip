"""Public update operations for Soundbar; JSON conversion happens here."""

from pathlib import Path

from . import check
from .check import schedule_checks
from .process import start_update
from .storage import status_payload


def status(root: Path) -> dict:
    return status_payload(check.status(root))


def check_for_updates(root: Path, force: bool = False) -> dict:
    check.check_for_updates(root, force=force)
    return status(root)
