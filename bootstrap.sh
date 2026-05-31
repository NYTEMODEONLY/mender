#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HERMES_HOME="$ROOT/home"
export HERMES_INSTALL_DIR="$ROOT/hermes-agent"
MENDER_RUNTIME_DIR="$ROOT/runtime"
MENDER_INSTALL_HOME="${TMPDIR:-/tmp}/mender-install-home-${UID:-user}"
export COPYFILE_DISABLE=1
export UV_LINK_MODE=copy
export UV_PYTHON_INSTALL_DIR="$MENDER_RUNTIME_DIR/uv/python"
export UV_PYTHON_BIN_DIR="$MENDER_RUNTIME_DIR/uv/bin"
export UV_CACHE_DIR="$MENDER_INSTALL_HOME/uv-cache"
export UV_TOOL_DIR="$MENDER_RUNTIME_DIR/uv/tools"
export UV_PYTHON_PREFERENCE=only-managed
export PYTHONDONTWRITEBYTECODE=1

mkdir -p "$HERMES_HOME" "$ROOT/audit" "$MENDER_RUNTIME_DIR" "$MENDER_INSTALL_HOME"

if [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
  rm -rf "$HERMES_INSTALL_DIR"
  git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_INSTALL_DIR"
fi

cp -n "$ROOT/templates/.env.example" "$HERMES_HOME/.env" 2>/dev/null || true
cp -n "$ROOT/templates/config.yaml" "$HERMES_HOME/config.yaml" 2>/dev/null || true
cp -n "$ROOT/templates/SOUL.md" "$HERMES_HOME/SOUL.md" 2>/dev/null || true

find "$ROOT" "$MENDER_INSTALL_HOME" -name '._*' -delete 2>/dev/null || true
HOME="$MENDER_INSTALL_HOME" PATH="$MENDER_INSTALL_HOME/.local/bin:$MENDER_INSTALL_HOME/.cargo/bin:$PATH" \
  bash "$HERMES_INSTALL_DIR/scripts/install.sh" \
  --dir "$HERMES_INSTALL_DIR" \
  --hermes-home "$HERMES_HOME" \
  --skip-setup \
  --skip-browser

find "$ROOT" -name '._*' -delete 2>/dev/null || true
echo "Mender bootstrap complete. Run: bash mender.sh setup"
