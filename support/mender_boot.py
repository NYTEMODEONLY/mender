#!/usr/bin/env python3
"""Mender portable boot and audit helper."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
AUDIT_ROOT = ROOT / "audit"
HERMES = ROOT / "hermes-agent"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_capture(command: list[str], timeout: int = 8) -> dict:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-4000:],
        }
    except Exception as exc:
        return {"command": command, "error": repr(exc)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def network_probe() -> dict:
    result = {"target": "https://api.deepseek.com", "ok": False}
    try:
        with socket.create_connection(("api.deepseek.com", 443), timeout=5):
            result["tcp_443"] = True
    except Exception as exc:
        result["tcp_443"] = False
        result["error"] = repr(exc)
        return result
    try:
        req = urllib.request.Request("https://api.deepseek.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=8) as response:
            result["http_status"] = response.status
            result["ok"] = True
    except Exception as exc:
        result["http_error"] = repr(exc)
        # TCP success is enough to prove basic internet/reachability.
        result["ok"] = True
    return result


def safe_host_id(profile: dict) -> str:
    material = "|".join(
        str(profile.get(k, ""))
        for k in ("hostname", "system", "release", "machine", "node_uuid")
    )
    return hashlib.sha256(material.encode("utf-8", "replace")).hexdigest()[:16]


def collect_profile() -> dict:
    node_uuid = ""
    mac = uuid.getnode()
    if (mac >> 40) % 2 == 0:
        node_uuid = f"{mac:012x}"
    profile = {
        "collected_at": now(),
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "user": getpass.getuser(),
        "cwd": os.getcwd(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.replace("\n", " "),
        "node_uuid": node_uuid,
        "mender_root": str(ROOT),
        "hermes_home": str(HOME),
        "hermes_agent": str(HERMES),
    }
    profile["host_id"] = safe_host_id(profile)
    return profile


def hermes_bin(system: str) -> Path:
    if system == "Windows":
        return HERMES / "venv" / "Scripts" / "hermes.exe"
    return HERMES / "venv" / "bin" / "hermes"


def hermes_python(system: str) -> Path:
    if system == "Windows":
        return HERMES / "venv" / "Scripts" / "python.exe"
    return HERMES / "venv" / "bin" / "python"


def install_snapshot(system: str) -> dict:
    return {
        "root_exists": ROOT.exists(),
        "home_exists": HOME.exists(),
        "config_exists": (HOME / "config.yaml").exists(),
        "env_exists": (HOME / ".env").exists(),
        "hermes_repo_exists": (HERMES / ".git").exists(),
        "hermes_bin": str(hermes_bin(system)),
        "hermes_bin_exists": hermes_bin(system).exists(),
        "hermes_python": str(hermes_python(system)),
        "hermes_python_exists": hermes_python(system).exists(),
        "git_head": run_capture(["git", "-C", str(HERMES), "rev-parse", "--short", "HEAD"]),
        "git_status": run_capture(["git", "-C", str(HERMES), "status", "--short"], timeout=12),
    }


def drive_snapshot(system: str) -> dict:
    snap: dict = {"root": str(ROOT)}
    try:
        usage = os.statvfs(ROOT)
        snap["free_bytes"] = usage.f_bavail * usage.f_frsize
        snap["total_bytes"] = usage.f_blocks * usage.f_frsize
    except Exception as exc:
        snap["statvfs_error"] = repr(exc)
    if system == "Darwin":
        snap["mount"] = run_capture(["mount"], timeout=8)
        snap["diskutil"] = run_capture(["diskutil", "info", str(ROOT)], timeout=8)
    elif system == "Windows":
        snap["volume"] = run_capture(["cmd", "/c", "wmic logicaldisk get caption,filesystem,freespace,size,volumename"], timeout=8)
    else:
        snap["mount"] = run_capture(["mount"], timeout=8)
    return snap


def command_inventory(system: str) -> list[dict]:
    if system == "Darwin":
        commands = [
            ["sw_vers"],
            ["uname", "-a"],
            ["diskutil", "list"],
            ["df", "-h"],
            ["ifconfig"],
            ["system_profiler", "SPHardwareDataType", "SPStorageDataType"],
        ]
    elif system == "Windows":
        commands = [
            ["cmd", "/c", "ver"],
            ["whoami"],
            ["wmic", "computersystem", "get", "model,manufacturer,totalphysicalmemory"],
            ["wmic", "diskdrive", "get", "model,size,status"],
            ["ipconfig", "/all"],
        ]
    else:
        commands = [
            ["uname", "-a"],
            ["cat", "/etc/os-release"],
            ["df", "-h"],
            ["lsblk", "-f"],
            ["ip", "addr"],
        ]
    return [run_capture(cmd) for cmd in commands]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, sort_keys=True) + "\n")


def ensure_mender_files() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "logs").mkdir(exist_ok=True)
    (HOME / "sessions").mkdir(exist_ok=True)
    (HOME / "skills").mkdir(exist_ok=True)
    templates = ROOT / "templates"
    env_path = HOME / ".env"
    if not env_path.exists():
        source = templates / ".env.example"
        if source.exists():
            env_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("DEEPSEEK_API_KEY=\n", encoding="utf-8")
    config_path = HOME / "config.yaml"
    if not config_path.exists() and (templates / "config.yaml").exists():
        config_path.write_text((templates / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    soul_path = HOME / "SOUL.md"
    if not soul_path.exists() and (templates / "SOUL.md").exists():
        soul_path.write_text((templates / "SOUL.md").read_text(encoding="utf-8"), encoding="utf-8")
    readme = AUDIT_ROOT / "README.md"
    if not readme.exists():
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "# Mender Audit Logs\n\n"
            "Each folder is `audit/<host-id>/<timestamp>/` and contains startup inventory, "
            "event logs, and terminal transcript data when available.\n",
            encoding="utf-8",
        )


def session_paths(profile: dict) -> dict:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    host_dir = AUDIT_ROOT / profile["host_id"]
    session_dir = host_dir / stamp
    return {
        "host_dir": host_dir,
        "session_dir": session_dir,
        "startup_json": session_dir / "startup.json",
        "events_jsonl": session_dir / "events.jsonl",
        "terminal_log": session_dir / "terminal.log",
    }


def cmd_start(args: argparse.Namespace) -> int:
    ensure_mender_files()
    profile = collect_profile()
    paths = session_paths(profile)
    env_values = load_env_file(HOME / ".env")
    inventory = command_inventory(profile["system"]) if not args.no_inventory else []
    payload = {
        "event": "mender_startup",
        "profile": profile,
        "inventory": inventory,
        "install": install_snapshot(profile["system"]),
        "drive": drive_snapshot(profile["system"]),
        "network": network_probe(),
        "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY") or env_values.get("DEEPSEEK_API_KEY")),
        "hermes_bin": str(hermes_bin(profile["system"])),
    }
    write_json(paths["startup_json"], payload)
    append_jsonl(paths["events_jsonl"], {"ts": now(), **payload})
    latest = AUDIT_ROOT / "latest-session.json"
    write_json(latest, {k: str(v) for k, v in paths.items()} | {"host_id": profile["host_id"]})

    print("")
    print("Mender startup")
    print("--------------")
    print(f"Host: {profile['hostname']} ({profile['system']} {profile['release']}, {profile['machine']})")
    print(f"Host audit id: {profile['host_id']}")
    print(f"Audit folder: {paths['session_dir']}")
    print(f"Hermes home: {HOME}")
    print("")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not loaded. Add it to Mender/home/.env or your shell before online use.")
    if payload["network"].get("ok"):
        print("DeepSeek network probe: reachable")
    else:
        print("DeepSeek network probe: not reachable")
    print("When Hermes opens, Mender's role is computer repair. Ask for diagnosis first; approve repairs deliberately.")
    print("")
    return 0


def latest_paths() -> dict | None:
    latest = AUDIT_ROOT / "latest-session.json"
    if not latest.exists():
        return None
    return json.loads(latest.read_text(encoding="utf-8"))


def cmd_event(args: argparse.Namespace) -> int:
    data = latest_paths()
    if not data:
        return 0
    append_jsonl(Path(data["events_jsonl"]), {"ts": now(), "event": args.name, "detail": args.detail})
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    data = latest_paths()
    if not data:
        return 0
    session_dir = Path(data["session_dir"])
    manifest = {
        "event": "mender_finish",
        "finished_at": now(),
        "host_id": data.get("host_id"),
        "files": {},
    }
    for name in ("startup_json", "events_jsonl", "terminal_log"):
        path = Path(data[name])
        manifest["files"][name] = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "sha256": sha256_file(path) if path.exists() else "",
        }
    write_json(session_dir / "manifest.json", manifest)
    append_jsonl(Path(data["events_jsonl"]), {"ts": now(), "event": "mender_finish", "detail": manifest})
    print(f"Audit manifest: {session_dir / 'manifest.json'}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    ensure_mender_files()
    profile = collect_profile()
    env_values = load_env_file(HOME / ".env")
    report = {
        "event": "mender_doctor",
        "profile": profile,
        "install": install_snapshot(profile["system"]),
        "drive": drive_snapshot(profile["system"]),
        "network": network_probe(),
        "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY") or env_values.get("DEEPSEEK_API_KEY")),
    }
    path = AUDIT_ROOT / "doctor-latest.json"
    write_json(path, report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    checks = [
        ("Hermes repo", report["install"]["hermes_repo_exists"]),
        ("Hermes executable", report["install"]["hermes_bin_exists"]),
        ("Hermes config", report["install"]["config_exists"]),
        ("DeepSeek API key", report["deepseek_key_present"]),
        ("DeepSeek network", report["network"].get("ok", False)),
    ]
    print("Mender doctor")
    print("-------------")
    for label, ok in checks:
        print(f"{label}: {'ok' if ok else 'missing'}")
    print(f"Report: {path}")
    return 0 if all(bool(ok) for _, ok in checks if _ != "DeepSeek API key") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mender portable boot helper")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--no-inventory", action="store_true")
    start.set_defaults(func=cmd_start)
    event = sub.add_parser("event")
    event.add_argument("name")
    event.add_argument("detail", nargs="?", default="")
    event.set_defaults(func=cmd_event)
    finish = sub.add_parser("finish")
    finish.set_defaults(func=cmd_finish)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
