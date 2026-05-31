#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HERMES_HOME="$ROOT/home"
export HERMES_INSTALL_DIR="$ROOT/hermes-agent"
export COPYFILE_DISABLE=1
export UV_LINK_MODE=copy

mkdir -p "$HERMES_HOME" "$ROOT/audit" "$ROOT/runtime"

if [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
  rm -rf "$HERMES_INSTALL_DIR"
  git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_INSTALL_DIR"
fi

cp -n "$ROOT/templates/.env.example" "$HERMES_HOME/.env" 2>/dev/null || true
cp -n "$ROOT/templates/config.yaml" "$HERMES_HOME/config.yaml" 2>/dev/null || true
cp -n "$ROOT/templates/SOUL.md" "$HERMES_HOME/SOUL.md" 2>/dev/null || true

bash "$HERMES_INSTALL_DIR/scripts/install.sh" \
  --dir "$HERMES_INSTALL_DIR" \
  --hermes-home "$HERMES_HOME" \
  --skip-setup \
  --skip-browser

find "$ROOT" -name '._*' -delete 2>/dev/null || true
echo "Mender bootstrap complete. Add DEEPSEEK_API_KEY to home/.env, then run: bash mender.sh"

