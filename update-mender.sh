#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE_URL="${MENDER_ARCHIVE_URL:-https://github.com/NYTEMODEONLY/mender/archive/refs/heads/main.tar.gz}"
STATE_EXCLUDES=(
  --exclude ".git/"
  --exclude "home/"
  --exclude "audit/"
  --exclude "hermes-agent/"
  --exclude "runtime/"
  --exclude "__pycache__/"
  --exclude "._*"
  --exclude ".DS_Store"
)

ensure_tools() {
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "$tool is required for Mender self-update."
      exit 1
    fi
  done
}

make_executable() {
  chmod +x \
    "$ROOT/mender" \
    "$ROOT/Mender.command" \
    "$ROOT/Mender.desktop" \
    "$ROOT/Mender.app/Contents/MacOS/Mender" \
    "$ROOT/bootstrap.sh" \
    "$ROOT/mender.sh" \
    "$ROOT/update-mender.sh" \
    "$ROOT/update-hermes.sh" \
    "$ROOT/scripts/smoke-test.sh" \
    "$ROOT/scripts/static-check.py" \
    "$ROOT/support/mender_boot.py" \
    "$ROOT/Start-Mender.command" 2>/dev/null || true
}

if [ -d "$ROOT/.git" ]; then
  ensure_tools git
  git -C "$ROOT" pull --ff-only origin "${MENDER_BRANCH:-main}"
  make_executable
  find "$ROOT" -name '._*' -delete 2>/dev/null || true
  echo "Mender updated from Git."
  exit 0
fi

ensure_tools curl tar rsync
tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

archive="$tmp_dir/mender.tar.gz"
src="$tmp_dir/src"
mkdir -p "$src"
curl -fsSL "$ARCHIVE_URL" -o "$archive"
tar -xzf "$archive" -C "$src" --strip-components 1
rsync -a --delete "${STATE_EXCLUDES[@]}" "$src/" "$ROOT/"
make_executable
find "$ROOT" -name '._*' -delete 2>/dev/null || true
echo "Mender updated from GitHub archive."
