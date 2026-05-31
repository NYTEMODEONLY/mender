#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export MENDER_SMOKE_FAST=1
export MENDER_SKIP_NETWORK_PROBE=1

smoke_step() {
  printf 'mender smoke: %s\n' "$1"
}

smoke_step "shell syntax"
bash -n bootstrap.sh
bash -n mender
bash -n Mender.command
bash -n Mender.app/Contents/MacOS/Mender
bash -n mender.sh
bash -n update-mender.sh
bash -n update-hermes.sh
smoke_step "python syntax"
python3 -m py_compile support/mender_boot.py
smoke_step "static checks"
python3 scripts/static-check.py
if command -v pwsh >/dev/null 2>&1; then
  smoke_step "powershell syntax with pwsh"
  pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/check-powershell.ps1
elif command -v powershell >/dev/null 2>&1; then
  smoke_step "powershell syntax with powershell"
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-powershell.ps1
fi

tmp_home="$(mktemp -d)"
tmp_audit="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_home" "$tmp_audit"
}
trap cleanup EXIT

mkdir -p "$tmp_home" "$tmp_audit"
MENDER_SMOKE_ROOT="$ROOT"

smoke_step "setup"
python3 support/mender_boot.py setup --provider deepseek --model deepseek-v4-pro --skip-key > "$tmp_audit/setup.txt"
smoke_step "prelaunch"
DEEPSEEK_API_KEY=smoke-key python3 support/mender_boot.py prelaunch --no-prompt
smoke_step "config assertions"
python3 - <<'PY'
from pathlib import Path
config = Path("home/config.yaml").read_text(encoding="utf-8")
assert 'provider: "deepseek"' in config
assert 'default: "deepseek-v4-pro"' in config
PY

smoke_step "doctor"
python3 support/mender_boot.py doctor --json > "$tmp_audit/doctor.json"
smoke_step "doctor assertions"
python3 - <<'PY' "$tmp_audit/doctor.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_doctor"
assert "install" in data
assert "network" in data
assert data["llm"]["provider"] == "deepseek"
PY

smoke_step "start"
python3 support/mender_boot.py start --no-inventory > "$tmp_audit/start.txt"
smoke_step "startup assertions"
test -f audit/latest-session.json
test -f audit/sessions.jsonl
latest_prompt="$(python3 - <<'PY'
import json
print(json.load(open("audit/latest-session.json"))["startup_prompt"])
PY
)"
test -f "$latest_prompt"
grep -q "Required Opening Sequence" "$latest_prompt"
active_soul="$(python3 - <<'PY'
import json
print(json.load(open("audit/latest-session.json"))["active_soul"])
PY
)"
test -f "$active_soul"
grep -q "Active Mender Repair Session" "$active_soul"
grep -q "Required Opening Sequence" "$active_soul"
grep -q "Audit Note Command" "$active_soul"
smoke_step "event note and finish"
python3 support/mender_boot.py event smoke "ok"
python3 support/mender_boot.py note verification "smoke note ok"
notes_path="$(python3 - <<'PY'
import json
print(json.load(open("audit/latest-session.json"))["notes_jsonl"])
PY
)"
test -f "$notes_path"
grep -q "smoke note ok" "$notes_path"
python3 support/mender_boot.py finish
smoke_step "audit"
python3 support/mender_boot.py audit --json > "$tmp_audit/audit.json"
smoke_step "audit assertions"
python3 - <<'PY' "$tmp_audit/audit.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert isinstance(data, list)
assert data
assert "startup_prompt" in data[-1]
assert "active_soul" in data[-1]
assert "notes_jsonl" in data[-1]
PY
smoke_step "ready"
python3 support/mender_boot.py ready --json > "$tmp_audit/ready.json" || true
smoke_step "ready assertions"
python3 - <<'PY' "$tmp_audit/ready.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_ready"
assert "ready" in data
PY

echo "mender smoke tests passed"
