"""Discover stable releases and download their published installation packages."""

import json
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import DEFAULT_CONFIG, UpdateConfig
from .constants import ARCHIVE_FILE, GITHUB_API, GITHUB_HEADERS, PACKAGE_ASSET, REPOSITORY
from .entities import Release, Version
from .errors import UpdateError


def latest_release(config: UpdateConfig = DEFAULT_CONFIG) -> Release:
    with request(GITHUB_API + "/releases/latest", config.request_timeout) as response:
        data = json.loads(response.read(config.response_limit))
    tag = data["tag_name"]
    version = Version.parse(tag)
    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("GitHub did not return a stable published release.")
    assets = [asset for asset in data.get("assets", [])
              if asset.get("name") == PACKAGE_ASSET and asset.get("state") == "uploaded"]
    if len(assets) != 1 or not isinstance(assets[0].get("id"), int) or assets[0]["id"] <= 0:
        raise UpdateError(f"Release {tag} does not contain an installable {PACKAGE_ASSET} package.")
    return Release(version, tag, data["id"],
                   f"https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}", assets[0]["id"])


def download_release(release: Release, work: Path, config: UpdateConfig = DEFAULT_CONFIG) -> Path:
    if not release.asset_id:
        raise UpdateError("Check for updates again to select an installation package.")
    archive = work / ARCHIVE_FILE
    deadline = time.monotonic() + config.download_deadline
    url = GITHUB_API + f"/releases/assets/{release.asset_id}"
    with request(url, config.download_timeout, accept="application/octet-stream") as response, archive.open("wb") as output:
        size = 0
        while chunk := response.read(config.download_chunk_size):
            size += len(chunk)
            if size > config.download_limit or time.monotonic() > deadline:
                raise UpdateError("Release download exceeded its size or time limit.")
            output.write(chunk)
    return archive


def request(url: str, timeout: int = DEFAULT_CONFIG.request_timeout, accept: str = GITHUB_HEADERS["Accept"]):
    return urlopen(Request(url, headers={**GITHUB_HEADERS, "Accept": accept}), timeout=timeout)
