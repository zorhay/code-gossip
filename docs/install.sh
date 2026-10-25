#!/bin/bash
# Download a release package and delegate installation to its installer.
set -euo pipefail

fail() {
  printf 'Code Gossip: %s\n' "$1" >&2
  exit 1
}

main() {
  for argument in "$@"; do
    case "$argument" in
      --de|--dev*) fail 'For development, run install.sh --dev from your permanent checkout.' ;;
    esac
  done
  [ "$(uname -s)" = Darwin ] || fail 'Installation requires macOS.'
  for dependency in python3 jq curl unzip; do
    command -v "$dependency" >/dev/null || fail "Missing $dependency. Install prerequisites first (brew install python jq)."
  done

  install_dir=$(mktemp -d "${TMPDIR:-/tmp}/code-gossip-install.XXXXXX")
  trap 'rm -rf "$install_dir"' EXIT
  printf 'Downloading the latest Code Gossip installation package...\n'
  curl -fsSL --connect-timeout 15 --max-time 120 \
    https://github.com/zorhay/code-gossip/releases/latest/download/code-gossip.zip \
    -o "$install_dir/code-gossip.zip" || fail 'Download failed. Check your connection and that the latest release workflow has finished.'
  unzip -q "$install_dir/code-gossip.zip" -d "$install_dir"
  /bin/bash "$install_dir/release/install.sh" "$@"
}

# Keep execution last so a truncated script cannot start an installation.
main "$@"
