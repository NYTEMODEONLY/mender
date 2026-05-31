#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HERMES_HOME="$SCRIPT_DIR/home"
export COPYFILE_DISABLE=1
export UV_LINK_MODE=copy
export PYTHONDONTWRITEBYTECODE=1

if [ ! -d "$SCRIPT_DIR/hermes-agent/.git" ]; then
  git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$SCRIPT_DIR/hermes-agent"
fi

cd "$SCRIPT_DIR/hermes-agent"
git pull --ff-only origin main
bash scripts/install.sh --dir "$SCRIPT_DIR/hermes-agent" --hermes-home "$SCRIPT_DIR/home" --skip-setup --skip-browser
find "$SCRIPT_DIR" -name '._*' -delete 2>/dev/null || true
echo "Mender/Hermes updated."
