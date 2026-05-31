#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MENDER_ROOT="$SCRIPT_DIR"
export HERMES_HOME="$MENDER_ROOT/home"
export HERMES_INSTALL_DIR="$MENDER_ROOT/hermes-agent"
export COPYFILE_DISABLE=1
export UV_LINK_MODE=copy
export PYTHONDONTWRITEBYTECODE=1

if [ -f "$HERMES_HOME/.env" ]; then
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value%$'\r'}"
    case "$key" in
      ""|\#*) continue ;;
      export\ *) key="${key#export }" ;;
    esac
    if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      export "$key=$value"
    fi
  done < "$HERMES_HOME/.env"
fi

BOOT_PY="$HERMES_INSTALL_DIR/venv/bin/python"
if [ ! -x "$BOOT_PY" ]; then
  BOOT_PY="$(command -v python3 || command -v python || true)"
fi

ensure_hermes_source() {
  if [ ! -d "$HERMES_INSTALL_DIR/.git" ]; then
    if ! command -v git >/dev/null 2>&1; then
      echo "Git is required to bootstrap Hermes Agent into $HERMES_INSTALL_DIR."
      exit 1
    fi
    echo "Hermes Agent source is missing. Cloning NousResearch/hermes-agent..."
    rm -rf "$HERMES_INSTALL_DIR"
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_INSTALL_DIR"
  fi
}

case "${1:-start}" in
  doctor)
    if [ -z "$BOOT_PY" ]; then
      echo "No Python runtime found for Mender doctor."
      exit 1
    fi
    "$BOOT_PY" "$MENDER_ROOT/support/mender_boot.py" doctor
    exit $?
    ;;
  doctor-json)
    if [ -z "$BOOT_PY" ]; then
      echo "No Python runtime found for Mender doctor."
      exit 1
    fi
    "$BOOT_PY" "$MENDER_ROOT/support/mender_boot.py" doctor --json
    exit $?
    ;;
  ready)
    if [ -z "$BOOT_PY" ]; then
      echo "No Python runtime found for Mender readiness check."
      exit 1
    fi
    "$BOOT_PY" "$MENDER_ROOT/support/mender_boot.py" ready
    exit $?
    ;;
  set-key)
    if [ -z "$BOOT_PY" ]; then
      echo "No Python runtime found for Mender key setup."
      exit 1
    fi
    "$BOOT_PY" "$MENDER_ROOT/support/mender_boot.py" set-key
    exit $?
    ;;
  audit)
    if [ -z "$BOOT_PY" ]; then
      echo "No Python runtime found for Mender audit."
      exit 1
    fi
    shift || true
    "$BOOT_PY" "$MENDER_ROOT/support/mender_boot.py" audit "$@"
    exit $?
    ;;
  update)
    exec bash "$MENDER_ROOT/update-mender.sh"
    ;;
  start|"")
    ;;
  *)
    echo "Usage: $0 [start|doctor|doctor-json|ready|set-key|audit|update]"
    exit 2
    ;;
esac

if [ ! -x "$HERMES_INSTALL_DIR/venv/bin/hermes" ]; then
  ensure_hermes_source
  echo "Hermes runtime is missing. Installing/updating on this computer..."
  bash "$HERMES_INSTALL_DIR/scripts/install.sh" \
    --dir "$HERMES_INSTALL_DIR" \
    --hermes-home "$HERMES_HOME" \
    --skip-setup \
    --skip-browser
fi

"$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" start
"$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" event hermes_launch "starting Hermes chat"

if command -v script >/dev/null 2>&1; then
  latest_log="$("$HERMES_INSTALL_DIR/venv/bin/python" - <<'PY'
import json, pathlib
p = pathlib.Path(__import__("os").environ["MENDER_ROOT"]) / "audit" / "latest-session.json"
print(json.loads(p.read_text())["terminal_log"])
PY
)"
  if script --version >/dev/null 2>&1; then
    script_cmd=(script -q -c "\"$HERMES_INSTALL_DIR/venv/bin/hermes\" chat --source mender --checkpoints" "$latest_log")
  else
    script_cmd=(script -q "$latest_log" "$HERMES_INSTALL_DIR/venv/bin/hermes" chat --source mender --checkpoints)
  fi
  if "${script_cmd[@]}"; then
    "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" event hermes_exit "exit=0"
    "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" finish
  else
    code=$?
    "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" event hermes_exit "exit=$code"
    "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" finish
    exit "$code"
  fi
else
  set +e
  "$HERMES_INSTALL_DIR/venv/bin/hermes" chat --source mender --checkpoints
  code=$?
  set -e
  "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" event hermes_exit "exit=$code"
  "$HERMES_INSTALL_DIR/venv/bin/python" "$MENDER_ROOT/support/mender_boot.py" finish
  exit "$code"
fi
