"""Keep release checks offline in disposable subprocess test installations."""
import io
import json
import os
from pathlib import Path
from urllib.error import URLError
import urllib.request

_urlopen = urllib.request.urlopen


def offline_urlopen(request, *args, **kwargs):
    url = request.full_url if hasattr(request, "full_url") else request
    if url.startswith("https://api.github.com/repos/zorhay/code-gossip/"):
        fixture = os.environ.get("TEST_RELEASE_DIRECTORY")
        if not fixture:
            raise URLError("Release checks disabled in tests")
        root = Path(fixture)
        if url.endswith("/releases/latest"):
            return (root / "release.json").open("rb")
        if "/commits/" in url:
            return io.BytesIO(json.dumps({"sha": "a" * 40}).encode())
        if url.endswith("/zipball/" + "a" * 40):
            return (root / "release.zip").open("rb")
        raise AssertionError("Unexpected release URL: " + url)
    return _urlopen(request, *args, **kwargs)


urllib.request.urlopen = offline_urlopen
