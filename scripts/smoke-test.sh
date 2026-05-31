#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash -n bootstrap.sh
bash -n mender
bash -n Mender.command
bash -n Mender.app/Contents/MacOS/Mender
bash -n mender.sh
bash -n update-mender.sh
python3 -m py_compile support/mender_boot.py
python3 scripts/static-check.py
if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/check-powershell.ps1
elif command -v powershell >/dev/null 2>&1; then
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

python3 support/mender_boot.py setup --provider deepseek --model deepseek-v4-pro --skip-key > "$tmp_audit/setup.txt"
python3 - <<'PY'
from pathlib import Path
config = Path("home/config.yaml").read_text(encoding="utf-8")
assert 'provider: "deepseek"' in config
assert 'default: "deepseek-v4-pro"' in config
PY

python3 support/mender_boot.py doctor --json > "$tmp_audit/doctor.json"
python3 - <<'PY' "$tmp_audit/doctor.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_doctor"
assert "install" in data
assert "network" in data
assert data["llm"]["provider"] == "deepseek"
PY

python3 support/mender_boot.py start --no-inventory > "$tmp_audit/start.txt"
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
python3 support/mender_boot.py event smoke "ok"
python3 support/mender_boot.py finish
python3 support/mender_boot.py audit --json > "$tmp_audit/audit.json"
python3 - <<'PY' "$tmp_audit/audit.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert isinstance(data, list)
assert data
assert "startup_prompt" in data[-1]
assert "active_soul" in data[-1]
PY
python3 support/mender_boot.py ready --json > "$tmp_audit/ready.json" || true
python3 - <<'PY' "$tmp_audit/ready.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_ready"
assert "ready" in data
PY

echo "mender smoke tests passed"
