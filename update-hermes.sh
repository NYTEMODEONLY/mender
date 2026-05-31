#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HERMES_HOME="$SCRIPT_DIR/home"
export HERMES_INSTALL_DIR="$SCRIPT_DIR/hermes-agent"
MENDER_INSTALL_HOME="${TMPDIR:-/tmp}/mender-install-home-${UID:-user}"
export COPYFILE_DISABLE=1
export UV_LINK_MODE=copy
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$MENDER_INSTALL_HOME"

if ! command -v git >/dev/null 2>&1; then
  echo "Git is required to update Hermes Agent."
  exit 1
fi

if [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
  rm -rf "$HERMES_INSTALL_DIR"
  git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_INSTALL_DIR"
fi

cd "$HERMES_INSTALL_DIR"
git pull --ff-only origin main
HOME="$MENDER_INSTALL_HOME" PATH="$MENDER_INSTALL_HOME/.local/bin:$MENDER_INSTALL_HOME/.cargo/bin:$PATH" \
  bash scripts/install.sh --dir "$HERMES_INSTALL_DIR" --hermes-home "$HERMES_HOME" --skip-setup --skip-browser
find "$SCRIPT_DIR" -name '._*' -delete 2>/dev/null || true
echo "Hermes Agent updated for Mender."
