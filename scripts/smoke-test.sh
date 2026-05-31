#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash -n bootstrap.sh
bash -n mender.sh
bash -n update-mender.sh
python3 -m py_compile support/mender_boot.py

tmp_home="$(mktemp -d)"
tmp_audit="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_home" "$tmp_audit"
}
trap cleanup EXIT

mkdir -p "$tmp_home" "$tmp_audit"
MENDER_SMOKE_ROOT="$ROOT"

python3 support/mender_boot.py doctor --json > "$tmp_audit/doctor.json"
python3 - <<'PY' "$tmp_audit/doctor.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_doctor"
assert "install" in data
assert "network" in data
PY

python3 support/mender_boot.py start --no-inventory > "$tmp_audit/start.txt"
test -f audit/latest-session.json
python3 support/mender_boot.py event smoke "ok"
python3 support/mender_boot.py finish
python3 support/mender_boot.py ready --json > "$tmp_audit/ready.json" || true
python3 - <<'PY' "$tmp_audit/ready.json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["event"] == "mender_ready"
assert "ready" in data
PY

echo "mender smoke tests passed"

