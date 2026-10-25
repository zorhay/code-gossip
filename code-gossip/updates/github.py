"""GitHub release discovery, commit resolution, and archive downloads."""

from dataclasses import replace
import json
from pathlib import Path
import re
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import DEFAULT_CONFIG, UpdateConfig
from .constants import ARCHIVE_FILE, GITHUB_API, GITHUB_HEADERS, REPOSITORY
from .entities import Release, Version
from .errors import UpdateError


def latest_release(config: UpdateConfig = DEFAULT_CONFIG) -> Release:
    with request(GITHUB_API + "/releases/latest", config.request_timeout) as response:
        data = json.loads(response.read(config.response_limit))
    tag = data["tag_name"]
    version = Version.parse(tag)
    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("GitHub did not return a stable published release.")
    return Release(version, tag, data["id"],
                   f"https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}")


def resolve_release(release: Release, config: UpdateConfig = DEFAULT_CONFIG) -> Release:
    Version.parse(release.tag)
    with request(GITHUB_API + "/commits/" + quote(release.tag, safe=""), config.request_timeout) as response:
        commit = json.loads(response.read(config.response_limit))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError("GitHub returned an invalid release commit.")
    return replace(release, commit=commit)


def download_release(release: Release, work: Path, config: UpdateConfig = DEFAULT_CONFIG) -> Path:
    if not release.commit:
        raise UpdateError("Resolve the release commit before downloading its source.")
    archive = work / ARCHIVE_FILE
    deadline = time.monotonic() + config.download_deadline
    with request(GITHUB_API + "/zipball/" + release.commit, config.download_timeout) as response, archive.open("wb") as output:
        size = 0
        while chunk := response.read(config.download_chunk_size):
            size += len(chunk)
            if size > config.download_limit or time.monotonic() > deadline:
                raise UpdateError("Release download exceeded its size or time limit.")
            output.write(chunk)
    return archive


def request(url: str, timeout: int = DEFAULT_CONFIG.request_timeout):
    return urlopen(Request(url, headers=GITHUB_HEADERS), timeout=timeout)
