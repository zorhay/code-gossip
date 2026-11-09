"""Values exchanged by the update workflows; no persistence or processes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .errors import UpdateError


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
        if not match:
            raise UpdateError(f"Expected a stable major.minor.patch version, got {value!r}.")
        return cls(*map(int, match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class Release:
    version: Version
    tag: str
    id: int
    notes_url: str
    asset_id: int | None = None


@dataclass(frozen=True)
class Installation:
    version: str
    mode: str
    root: Path
    python: str
    integrations: dict[str, Path]


@dataclass(frozen=True)
class CheckResult:
    release: Release | None = None
    checked_at: float | None = None
    attempted_at: float | None = None
    error: str = ""


@dataclass
class UpdateProgress:
    phase: str = "idle"
    message: str = ""
    started_at: float | None = None
    work: Path | None = None
    guidance: str = ""

@dataclass(frozen=True)
class UpdateStatus:
    installed: str
    release: Release | None
    available: bool
    checked_at: float | None
    development: bool
    running: bool
    phase: str
    message: str
    guidance: str
    operation_id: float | None
