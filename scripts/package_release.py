#!/usr/bin/env python3
"""Package the checked-out release source; VERSION is generated from its tag."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code-gossip"))

from updates.constants import PACKAGE_ASSET
from updates.entities import Release, Version
from updates.source import extract_archive, validate_source


def build_package(root: Path, tag: str, output: Path) -> Path:
    release = Release(Version.parse(tag), tag, 0, "")
    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "install.sh", "LICENSE", "code-gossip"], cwd=root
    ).decode().split("\0")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in filter(None, files):
            if name != "code-gossip/VERSION":
                info = zipfile.ZipInfo.from_file(root / name, "release/" + name)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, (root / name).read_bytes())
        info = zipfile.ZipInfo("release/code-gossip/VERSION", (1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, str(release.version) + "\n")
    with tempfile.TemporaryDirectory(prefix="code-gossip-package-") as temporary:
        source = extract_archive(output, Path(temporary) / "source")
        validate_source(source, release)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag; the workflow checks out this tag before building")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / PACKAGE_ASSET)
    args = parser.parse_args()
    print(build_package(ROOT, args.tag, args.output))


if __name__ == "__main__":
    main()
