#!/bin/bash
# Download a release package and delegate installation to its installer.
set -euo pipefail

fail() {
  printf 'Code Gossip: %s\n' "$1" >&2
  exit 1
}

main() {
  local release_tag='' expected_version='' download_url release_label
  local installer_args=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --release)
        [ "$#" -ge 2 ] || fail '--release requires a stable version tag.'
        [ -z "$release_tag" ] || fail 'Pass --release only once.'
        [[ "$2" =~ ^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || fail '--release requires a stable version tag, for example 0.13.0.'
        release_tag="$2"
        expected_version="${release_tag#v}"
        shift 2 ;;
      *) installer_args+=("$1"); shift ;;
    esac
  done
  # Bash 3.2 treats an empty array as unset under nounset.
  set -- ${installer_args[@]+"${installer_args[@]}"}
  for argument in "$@"; do
    case "$argument" in
      --de|--dev*) fail 'For development, run install.sh --dev from your permanent checkout.' ;;
    esac
  done
  [ "$(uname -s)" = Darwin ] || fail 'Installation requires macOS.'
  for dependency in python3 jq curl; do
    command -v "$dependency" >/dev/null || fail "Missing $dependency. Install prerequisites first (brew install python jq)."
  done

  install_dir=$(mktemp -d "${TMPDIR:-/tmp}/code-gossip-install.XXXXXX")
  trap 'rm -rf "$install_dir"' EXIT
  if [ -n "$release_tag" ]; then
    download_url="https://github.com/zorhay/code-gossip/releases/download/$release_tag/code-gossip.zip"
    release_label="$release_tag"
  else
    download_url='https://github.com/zorhay/code-gossip/releases/latest/download/code-gossip.zip'
    release_label='latest'
  fi
  printf 'Downloading the %s Code Gossip installation package...\n' "$release_label"
  curl -fsSL --connect-timeout 15 --max-time 120 --max-filesize 268435456 \
    "$download_url" \
    -o "$install_dir/code-gossip.zip" || fail 'Download failed. Check your connection and that the requested release workflow has finished.'
  python3 -B - "$install_dir" "$expected_version" <<'PYTHON'
from pathlib import Path, PurePosixPath
import stat, sys, zipfile
root = Path(sys.argv[1])
with zipfile.ZipFile(root / "code-gossip.zip") as bundle:
    if sys.argv[2] and bundle.read("release/code-gossip/VERSION").decode().strip() != sys.argv[2]:
        sys.exit("Installation package does not match the requested release")
    members = bundle.infolist()
    if len(members) > 20000 or sum(m.file_size for m in members) > 512 * 1024 * 1024:
        sys.exit("Installation package is too large")
    for member in members:
        path, mode = PurePosixPath(member.filename), member.external_attr >> 16
        if (not member.filename.startswith("release/") or ".." in path.parts or "\\" in member.filename
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            sys.exit("Unsafe installation package")
        target = Path(bundle.extract(member, root))
        target.chmod(0o755 if member.is_dir() or mode & 0o111 else 0o644)
PYTHON
  /bin/bash "$install_dir/release/install.sh" "$@"
}

# Keep execution last so a truncated script cannot start an installation.
main "$@"
