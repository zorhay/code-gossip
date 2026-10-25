#!/usr/bin/env python3
"""Validate an unmodified Git or downloaded release archive before publication."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code-gossip"))

from updates.entities import Release, Version
from updates.errors import UpdateError
from updates.source import extract_archive, validate_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="intended stable release tag, such as 0.9.1")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--ref", default="HEAD", help="Git commit or tag to archive (default: HEAD)")
    source.add_argument("--archive", type=Path, help="validate an already downloaded GitHub ZIP")
    args = parser.parse_args()
    try:
        release = Release(Version.parse(args.tag), args.tag, 0, "")
        with tempfile.TemporaryDirectory(prefix="code-gossip-release-check-") as temporary:
            work = Path(temporary)
            archive = args.archive or work / "release.zip"
            if args.archive is None:
                subprocess.run(["git", "archive", "--format=zip", "--prefix=release/",
                                f"--output={archive}", args.ref], cwd=ROOT, check=True)
            extracted = extract_archive(archive, work / "source")
            validate_source(extracted, release)
        print(f"Release {args.tag}: source archive and shipped version match.")
        return 0
    except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as error:
        print(f"Release validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
