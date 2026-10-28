#!/usr/bin/env python3
"""Verify the tested Pages artifact and its exact matching installer before deployment."""
import argparse
import json
from pathlib import Path
import zipfile

try:
    from .preview_content import digest
except ImportError:
    from preview_content import digest

def verify(site, package, tag, commit):
    build = json.loads((site / "build.json").read_text())
    if build["tag"] != tag or build["commit"] != commit:
        raise ValueError("Pages artifact does not belong to this release commit/tag")
    if build["packageSha256"] != digest(package.read_bytes()):
        raise ValueError("Pages artifact was not tested with this installation package")
    actual = {str(p.relative_to(site)) for p in site.rglob("*") if p.is_file()} - {"build.json"}
    if actual != set(build["files"]):
        raise ValueError("Pages artifact file list changed after testing")
    for name, expected in build["files"].items():
        path = site / name
        if not path.resolve().is_relative_to(site.resolve()) or digest(path.read_bytes()) != expected:
            raise ValueError(f"Pages artifact changed after testing: {name}")
    with zipfile.ZipFile(package) as bundle:
        if bundle.read("release/code-gossip/VERSION").decode().strip() != build["version"]:
            raise ValueError("Pages and installer versions differ")
        for name, expected in build["runtime"].items():
            if digest(bundle.read("release/code-gossip/" + name)) != expected:
                raise ValueError(f"Pages and installer sources differ: {name}")
    return build

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    verify(args.site, args.package, args.tag, args.commit)
    print("Pages artifact, installer, version, and source commit match.")

if __name__ == "__main__":
    main()
