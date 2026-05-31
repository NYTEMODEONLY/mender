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
import time
import uuid
import urllib.parse
import urllib.request
import zipfile
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


def save_env_value(path: Path, key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError("Environment values cannot contain newlines")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    out: list[str] = []
    replaced = False
    for raw in lines:
        stripped = raw.strip()
        prefix = "export " if stripped.startswith("export ") else ""
        comparable = stripped[7:].strip() if prefix else stripped
        if comparable.startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(raw)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def unquote_yaml_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def shell_quote(value: str) -> str:
    return json.dumps(value)


def base_config_yaml(*, provider: str, model: str, base_url: str, custom: bool = False) -> str:
    lines = [
        "model:",
        f"  default: {shell_quote(model)}",
        f"  provider: {shell_quote(provider)}",
        f"  base_url: {shell_quote(base_url)}",
        "",
        "terminal:",
        '  backend: "local"',
        '  cwd: "."',
        "  timeout: 180",
        "  docker_mount_cwd_to_workspace: false",
        "  lifetime_seconds: 300",
        "",
        "agent:",
        "  max_turns: 90",
        "",
    ]
    if custom:
        lines.extend(
            [
                "custom_providers:",
                "  - name: \"mender-custom\"",
                f"    base_url: {shell_quote(base_url)}",
                "    key_env: \"MENDER_CUSTOM_API_KEY\"",
                f"    model: {shell_quote(model)}",
                "    api_mode: \"chat_completions\"",
                "",
            ]
        )
    return "\n".join(lines)


def write_llm_config(provider_choice: str, model: str, base_url: str) -> tuple[str, str, str]:
    provider_choice = provider_choice.strip().lower()
    if provider_choice == "deepseek":
        provider = "deepseek"
        model = model or "deepseek-v4-pro"
        base_url = base_url or "https://api.deepseek.com/v1"
        key_env = "DEEPSEEK_API_KEY"
        custom = False
    elif provider_choice == "openrouter":
        provider = "openrouter"
        model = model or "deepseek/deepseek-v4-pro"
        base_url = base_url or "https://openrouter.ai/api/v1"
        key_env = "OPENROUTER_API_KEY"
        custom = False
    elif provider_choice == "custom":
        provider = "custom:mender-custom"
        model = model or "model-name"
        base_url = base_url or "https://example.com/v1"
        key_env = "MENDER_CUSTOM_API_KEY"
        custom = True
    else:
        raise ValueError(f"Unsupported provider choice: {provider_choice}")
    (HOME / "config.yaml").write_text(
        base_config_yaml(provider=provider, model=model, base_url=base_url, custom=custom),
        encoding="utf-8",
    )
    return provider, model, key_env


def llm_settings() -> dict:
    config_path = HOME / "config.yaml"
    settings = {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
    }
    if not config_path.exists():
        return settings

    section = ""
    for raw in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")) and raw.rstrip().endswith(":"):
            section = raw.strip().rstrip(":")
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = unquote_yaml_value(value)
        if section == "model" and key == "default":
            settings["model"] = value
        elif section == "model" and key == "provider":
            settings["provider"] = value
        elif section == "model" and key == "base_url":
            settings["base_url"] = value
        elif key == "key_env" and settings["provider"].startswith("custom:"):
            settings["key_env"] = value

    provider = settings["provider"]
    if provider == "deepseek":
        settings["key_env"] = "DEEPSEEK_API_KEY"
    elif provider == "openrouter":
        settings["key_env"] = "OPENROUTER_API_KEY"
    elif provider.startswith("custom:") and settings["key_env"] == "DEEPSEEK_API_KEY":
        settings["key_env"] = "MENDER_CUSTOM_API_KEY"
    return settings


def provider_key_present(settings: dict, env_values: dict[str, str]) -> bool:
    key_env = settings["key_env"]
    return bool(os.environ.get(key_env) or env_values.get(key_env))


def network_probe(base_url: str | None = None) -> dict:
    parsed = urllib.parse.urlparse(base_url or "https://api.deepseek.com")
    if not parsed.scheme:
        parsed = urllib.parse.urlparse(f"https://{base_url}")
    host = parsed.hostname or "api.deepseek.com"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    target = f"{parsed.scheme or 'https'}://{host}"
    result = {"target": target, "ok": False}
    if os.environ.get("MENDER_SKIP_NETWORK_PROBE"):
        return {"target": target, "ok": True, "skipped": True}
    try:
        with socket.create_connection((host, port), timeout=5):
            result["tcp_443"] = True
    except Exception as exc:
        result["tcp_443"] = False
        result["error"] = repr(exc)
        return result
    try:
        req = urllib.request.Request(target, method="HEAD")
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
    fast_probe = bool(os.environ.get("MENDER_SMOKE_FAST"))
    node_uuid = ""
    if not fast_probe:
        mac = uuid.getnode()
        if (mac >> 40) % 2 == 0:
            node_uuid = f"{mac:012x}"
    hostname = socket.gethostname()
    profile = {
        "collected_at": now(),
        "hostname": hostname,
        "fqdn": hostname if fast_probe else socket.getfqdn(),
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


def path_resolves_under(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().is_relative_to(parent.resolve())
    except Exception:
        return False


def install_snapshot(system: str) -> dict:
    python_path = hermes_python(system)
    python_resolved = python_path.resolve() if python_path.exists() else python_path
    snap = {
        "root_exists": ROOT.exists(),
        "home_exists": HOME.exists(),
        "config_exists": (HOME / "config.yaml").exists(),
        "env_exists": (HOME / ".env").exists(),
        "hermes_repo_exists": (HERMES / ".git").exists(),
        "hermes_bin": str(hermes_bin(system)),
        "hermes_bin_exists": hermes_bin(system).exists(),
        "hermes_python": str(python_path),
        "hermes_python_exists": python_path.exists(),
        "hermes_python_resolved": str(python_resolved),
        "hermes_python_on_drive": path_resolves_under(python_path, ROOT) if python_path.exists() else False,
        "hermes_python_usable": run_capture([str(python_path), "-V"], timeout=8).get("returncode") == 0
        if python_path.exists()
        else False,
    }
    if os.environ.get("MENDER_SMOKE_FAST"):
        snap["fast_probe"] = True
        return snap
    snap["git_head"] = run_capture(["git", "-C", str(HERMES), "rev-parse", "--short", "HEAD"])
    snap["git_status"] = run_capture(["git", "-C", str(HERMES), "status", "--short"], timeout=12)
    return snap


def drive_snapshot(system: str) -> dict:
    snap: dict = {"root": str(ROOT)}
    try:
        usage = os.statvfs(ROOT)
        snap["free_bytes"] = usage.f_bavail * usage.f_frsize
        snap["total_bytes"] = usage.f_blocks * usage.f_frsize
    except Exception as exc:
        snap["statvfs_error"] = repr(exc)
    if os.environ.get("MENDER_SMOKE_FAST"):
        snap["fast_probe"] = True
        return snap
    if system == "Darwin":
        snap["mount"] = run_capture(["mount"], timeout=8)
        snap["diskutil"] = run_capture(["diskutil", "info", str(ROOT)], timeout=8)
    elif system == "Windows":
        snap["volume"] = run_capture(["cmd", "/c", "wmic logicaldisk get caption,filesystem,freespace,size,volumename"], timeout=8)
        snap["volume_powershell"] = run_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID,VolumeName,FileSystem,FreeSpace,Size | ConvertTo-Json -Compress",
            ],
            timeout=12,
        )
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
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-ComputerInfo | Select-Object WindowsProductName,WindowsVersion,OsHardwareAbstractionLayer,CsManufacturer,CsModel,CsTotalPhysicalMemory | ConvertTo-Json -Compress",
            ],
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_DiskDrive | Select-Object Model,Size,Status,InterfaceType,MediaType | ConvertTo-Json -Compress",
            ],
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-NetIPConfiguration | ConvertTo-Json -Depth 4 -Compress",
            ],
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


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            items.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return items


def should_exclude_from_bundle(path: Path) -> bool:
    parts = set(path.parts)
    if path.name.startswith("._") or path.name == ".DS_Store" or "__MACOSX" in parts:
        return True
    if ".env" in parts or path.name == ".env":
        return True
    if "bundles" in parts and "audit" in parts:
        return True
    return False


def add_bundle_path(bundle: zipfile.ZipFile, path: Path, arc_prefix: str = "") -> None:
    if not path.exists() or should_exclude_from_bundle(path):
        return
    if path.is_file():
        arcname = Path(arc_prefix) / path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(arc_prefix) / path.name
        bundle.write(path, arcname.as_posix())
        return
    for item in path.rglob("*"):
        if item.is_file() and not should_exclude_from_bundle(item):
            arcname = Path(arc_prefix) / item.relative_to(ROOT)
            bundle.write(item, arcname.as_posix())


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
    persona_path = HOME / "MENDER_PERSONA.md"
    if not persona_path.exists():
        if soul_path.exists() and soul_path.read_text(encoding="utf-8", errors="replace").strip():
            persona_path.write_text(soul_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        elif (templates / "SOUL.md").exists():
            persona_path.write_text((templates / "SOUL.md").read_text(encoding="utf-8"), encoding="utf-8")
        else:
            persona_path.write_text("You are Mender, a portable computer-repair agent.\n", encoding="utf-8")
    if not soul_path.exists():
        soul_path.write_text(persona_path.read_text(encoding="utf-8"), encoding="utf-8")
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
        "startup_prompt": session_dir / "startup_prompt.md",
        "events_jsonl": session_dir / "events.jsonl",
        "notes_jsonl": session_dir / "notes.jsonl",
        "terminal_log": session_dir / "terminal.log",
    }


def startup_prompt_text(profile: dict, paths: dict, payload: dict) -> str:
    key_status = "present" if payload["llm_key_present"] else "missing"
    network_status = "reachable" if payload["network"].get("ok") else "not reachable"
    llm = payload["llm"]
    return f"""# Mender Startup Prompt

You are Mender, a portable computer-repair Hermes Agent running from this storage device.

## Connected Host

- Hostname: {profile["hostname"]}
- OS: {profile["system"]} {profile["release"]}
- Machine: {profile["machine"]}
- User: {profile["user"]}
- Host audit id: {profile["host_id"]}

## Session Audit

- Session folder: {paths["session_dir"]}
- Startup inventory: {paths["startup_json"]}
- Event log: {paths["events_jsonl"]}
- Repair notes: {paths["notes_jsonl"]}
- Terminal transcript: {paths["terminal_log"]}
- Active Hermes identity prompt: {HOME / "SOUL.md"}

## Readiness

- LLM provider: {llm["provider"]}
- LLM model: {llm["model"]}
- LLM key env: {llm["key_env"]} ({key_status})
- LLM network: {network_status}

## Required Opening Sequence

1. Confirm the symptom or repair goal with the user.
2. Review the startup inventory before proposing changes.
3. Diagnose with read-only commands first.
4. Explain every repair command before running it, including risk and rollback.
5. Record what changed, why, and how it was verified.

## Audit Note Command

Use Mender's note command whenever you inspect something important, make a change, verify a result, or decide not to proceed:

- macOS/Linux: `./mender note <category> "<detail>"`
- Windows: `mender.cmd note <category> "<detail>"`

Recommended categories: `symptom`, `diagnosis`, `command`, `change`, `verification`, `risk`, `rollback`, `handoff`.

Do not claim the computer is fixed until the relevant current-state evidence proves it.
"""


def write_active_soul(startup_text: str) -> dict:
    persona_path = HOME / "MENDER_PERSONA.md"
    active_soul_path = HOME / "SOUL.md"
    persona = persona_path.read_text(encoding="utf-8", errors="replace").strip()
    active_soul_path.write_text(
        persona
        + "\n\n---\n\n"
        + "# Active Mender Repair Session\n\n"
        + "This section is regenerated at every Mender launch and is loaded by Hermes as part "
        + "of the session identity prompt.\n\n"
        + startup_text.strip()
        + "\n",
        encoding="utf-8",
    )
    return {
        "persona_path": str(persona_path),
        "active_soul_path": str(active_soul_path),
        "active_soul_sha256": sha256_file(active_soul_path),
    }


def update_audit_index(profile: dict, paths: dict, payload: dict) -> None:
    host_dir = AUDIT_ROOT / "hosts"
    host_dir.mkdir(parents=True, exist_ok=True)
    host_record = {
        "host_id": profile["host_id"],
        "hostname": profile["hostname"],
        "fqdn": profile["fqdn"],
        "system": profile["system"],
        "release": profile["release"],
        "machine": profile["machine"],
        "first_seen": profile["collected_at"],
        "last_seen": profile["collected_at"],
        "last_session": str(paths["session_dir"]),
    }
    host_path = host_dir / f"{profile['host_id']}.json"
    if host_path.exists():
        existing = json.loads(host_path.read_text(encoding="utf-8"))
        host_record["first_seen"] = existing.get("first_seen", host_record["first_seen"])
    write_json(host_path, host_record)
    append_jsonl(
        AUDIT_ROOT / "sessions.jsonl",
        {
            "ts": now(),
            "host_id": profile["host_id"],
            "hostname": profile["hostname"],
            "system": profile["system"],
            "release": profile["release"],
            "machine": profile["machine"],
            "session_dir": str(paths["session_dir"]),
            "startup_json": str(paths["startup_json"]),
            "startup_prompt": str(paths["startup_prompt"]),
            "active_soul": payload["active_soul"]["active_soul_path"],
            "active_soul_sha256": payload["active_soul"]["active_soul_sha256"],
            "events_jsonl": str(paths["events_jsonl"]),
            "notes_jsonl": str(paths["notes_jsonl"]),
            "terminal_log": str(paths["terminal_log"]),
            "llm_provider": payload["llm"]["provider"],
            "llm_model": payload["llm"]["model"],
            "llm_key_env": payload["llm"]["key_env"],
            "llm_key_present": payload["llm_key_present"],
            "llm_network_ok": payload["network"].get("ok", False),
        },
    )


def cmd_start(args: argparse.Namespace) -> int:
    ensure_mender_files()
    profile = collect_profile()
    paths = session_paths(profile)
    paths["session_dir"].mkdir(parents=True, exist_ok=True)
    env_values = load_env_file(HOME / ".env")
    llm = llm_settings()
    inventory = command_inventory(profile["system"]) if not args.no_inventory else []
    payload = {
        "event": "mender_startup",
        "profile": profile,
        "inventory": inventory,
        "install": install_snapshot(profile["system"]),
        "drive": drive_snapshot(profile["system"]),
        "network": network_probe(llm["base_url"]),
        "llm": llm,
        "llm_key_present": provider_key_present(llm, env_values),
        "hermes_bin": str(hermes_bin(profile["system"])),
    }
    startup_text = startup_prompt_text(profile, paths, payload)
    paths["startup_prompt"].write_text(startup_text, encoding="utf-8")
    paths["notes_jsonl"].write_text("", encoding="utf-8")
    payload["active_soul"] = write_active_soul(startup_text)
    write_json(paths["startup_json"], payload)
    append_jsonl(paths["events_jsonl"], {"ts": now(), **payload})
    update_audit_index(profile, paths, payload)
    latest = AUDIT_ROOT / "latest-session.json"
    write_json(
        latest,
        {k: str(v) for k, v in paths.items()}
        | {"host_id": profile["host_id"], "active_soul": payload["active_soul"]["active_soul_path"]},
    )

    print("")
    print("Mender startup")
    print("--------------")
    print(f"Host: {profile['hostname']} ({profile['system']} {profile['release']}, {profile['machine']})")
    print(f"Host audit id: {profile['host_id']}")
    print(f"Audit folder: {paths['session_dir']}")
    print(f"Startup prompt: {paths['startup_prompt']}")
    print(f"Injected Hermes prompt: {payload['active_soul']['active_soul_path']}")
    print(f"Hermes home: {HOME}")
    print("")
    if not provider_key_present(llm, env_values):
        print(f"{llm['key_env']} is not loaded. Add it to Mender/home/.env or your shell before online use.")
    if payload["network"].get("ok"):
        print(f"{llm['provider']} network probe: reachable")
    else:
        print(f"{llm['provider']} network probe: not reachable")
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


def cmd_note(args: argparse.Namespace) -> int:
    data = latest_paths()
    if not data:
        print("No active Mender session. Start Mender before adding notes.", file=sys.stderr)
        return 1
    category = args.category.strip().lower()
    detail = " ".join(args.detail).strip()
    if not category or not detail:
        print("Usage: note <category> <detail>", file=sys.stderr)
        return 2
    note = {"ts": now(), "event": "mender_note", "category": category, "detail": detail}
    notes_path = Path(data.get("notes_jsonl") or Path(data["session_dir"]) / "notes.jsonl")
    append_jsonl(notes_path, note)
    append_jsonl(Path(data["events_jsonl"]), note)
    print(f"Recorded Mender note: {category}")
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
    for name in ("startup_json", "startup_prompt", "active_soul", "events_jsonl", "notes_jsonl", "terminal_log"):
        if name not in data:
            continue
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
    llm = llm_settings()
    report = {
        "event": "mender_doctor",
        "profile": profile,
        "install": install_snapshot(profile["system"]),
        "drive": drive_snapshot(profile["system"]),
        "network": network_probe(llm["base_url"]),
        "llm": llm,
        "llm_key_present": provider_key_present(llm, env_values),
    }
    path = AUDIT_ROOT / "doctor-latest.json"
    write_json(path, report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    checks = [
        ("Hermes repo", report["install"]["hermes_repo_exists"]),
        ("Hermes executable", report["install"]["hermes_bin_exists"]),
        ("Hermes Python on drive", report["install"]["hermes_python_on_drive"]),
        ("Hermes config", report["install"]["config_exists"]),
        (f"{llm['provider']} API key", report["llm_key_present"]),
        (f"{llm['provider']} network", report["network"].get("ok", False)),
    ]
    print("Mender doctor")
    print("-------------")
    for label, ok in checks:
        print(f"{label}: {'ok' if ok else 'missing'}")
    print(f"Report: {path}")
    return 0 if all(bool(ok) for _, ok in checks if not _.endswith(" API key")) else 1


def readiness_report() -> dict:
    ensure_mender_files()
    profile = collect_profile()
    env_values = load_env_file(HOME / ".env")
    llm = llm_settings()
    report = {
        "event": "mender_ready",
        "profile": profile,
        "install": install_snapshot(profile["system"]),
        "network": network_probe(llm["base_url"]),
        "llm": llm,
        "llm_key_present": provider_key_present(llm, env_values),
    }
    report["ready"] = bool(
        report["install"]["hermes_repo_exists"]
        and report["install"]["hermes_bin_exists"]
        and report["install"]["hermes_python_usable"]
        and report["install"]["config_exists"]
        and report["llm_key_present"]
        and report["network"].get("ok", False)
    )
    write_json(AUDIT_ROOT / "ready-latest.json", report)
    return report


def cmd_ready(args: argparse.Namespace) -> int:
    report = readiness_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Mender readiness")
        print("----------------")
        print(f"Hermes repo: {'ok' if report['install']['hermes_repo_exists'] else 'missing'}")
        print(f"Hermes executable: {'ok' if report['install']['hermes_bin_exists'] else 'missing'}")
        print(f"Hermes Python usable: {'ok' if report['install']['hermes_python_usable'] else 'missing'}")
        print(f"Hermes Python on drive: {'yes' if report['install']['hermes_python_on_drive'] else 'no'}")
        print(f"Hermes config: {'ok' if report['install']['config_exists'] else 'missing'}")
        print(f"LLM provider: {report['llm']['provider']}")
        print(f"LLM model: {report['llm']['model']}")
        print(f"{report['llm']['key_env']}: {'ok' if report['llm_key_present'] else 'missing'}")
        print(f"{report['llm']['provider']} network: {'ok' if report['network'].get('ok', False) else 'missing'}")
        print(f"Ready: {'yes' if report['ready'] else 'no'}")
        print(f"Report: {AUDIT_ROOT / 'ready-latest.json'}")
    return 0 if report["ready"] else 1


def cmd_llm_check(args: argparse.Namespace) -> int:
    ensure_mender_files()
    profile = collect_profile()
    env_values = load_env_file(HOME / ".env")
    llm = llm_settings()
    env = os.environ.copy()
    env.update(env_values)
    env["HERMES_HOME"] = str(HOME)
    env["HERMES_INSTALL_DIR"] = str(HERMES)
    prompt = args.prompt or "Reply with exactly: MENDER_ONLINE"
    expected = args.expected or "MENDER_ONLINE"
    report = {
        "event": "mender_llm_check",
        "checked_at": now(),
        "profile": profile,
        "llm": llm,
        "llm_key_present": provider_key_present(llm, env_values),
        "hermes_bin": str(hermes_bin(profile["system"])),
        "hermes_bin_exists": hermes_bin(profile["system"]).exists(),
        "prompt": prompt,
        "expected": expected,
        "ok": False,
    }
    start_time = time.monotonic()
    if not report["llm_key_present"]:
        report["error"] = f"{llm['key_env']} missing"
    elif not report["hermes_bin_exists"]:
        report["error"] = "Hermes executable missing"
    else:
        try:
            proc = subprocess.run(
                [
                    str(hermes_bin(profile["system"])),
                    "--oneshot",
                    prompt,
                    "--provider",
                    llm["provider"],
                    "--model",
                    llm["model"],
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
                env=env,
            )
            stdout = proc.stdout.strip()
            report["returncode"] = proc.returncode
            report["stdout_tail"] = stdout[-2000:]
            report["stderr_tail"] = proc.stderr.strip()[-2000:]
            report["ok"] = proc.returncode == 0 and expected in stdout
        except Exception as exc:
            report["error"] = repr(exc)
    report["duration_seconds"] = round(time.monotonic() - start_time, 3)
    write_json(AUDIT_ROOT / "llm-check-latest.json", report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Mender LLM check")
        print("----------------")
        print(f"Provider: {llm['provider']}")
        print(f"Model: {llm['model']}")
        print(f"Hermes executable: {'ok' if report['hermes_bin_exists'] else 'missing'}")
        print(f"{llm['key_env']}: {'ok' if report['llm_key_present'] else 'missing'}")
        print(f"Expected marker: {expected}")
        print(f"Result: {'ok' if report['ok'] else 'failed'}")
        print(f"Report: {AUDIT_ROOT / 'llm-check-latest.json'}")
    return 0 if report["ok"] else 1


def cmd_set_key(args: argparse.Namespace) -> int:
    ensure_mender_files()
    llm = llm_settings()
    env_name = args.env or llm["key_env"]
    value = args.value
    if not value:
        value = getpass.getpass(f"{env_name}: ").strip()
    if not value:
        print("No key provided; nothing changed.", file=sys.stderr)
        return 1
    save_env_value(HOME / ".env", env_name, value)
    print(f"Saved {env_name} to {HOME / '.env'}")
    return 0


def choose(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_mender_files()
    provider_choice = args.provider.strip().lower()
    if not provider_choice:
        print("Mender LLM setup")
        print("----------------")
        print("1. DeepSeek direct (recommended): deepseek-v4-pro")
        print("2. OpenRouter: any OpenRouter model")
        print("3. Custom OpenAI-compatible endpoint")
        selected = choose("Choose provider", "1")
        provider_choice = {"1": "deepseek", "2": "openrouter", "3": "custom"}.get(selected, selected).strip().lower()

    if provider_choice == "deepseek":
        model = args.model or choose("Model", "deepseek-v4-pro")
        base_url = args.base_url or "https://api.deepseek.com/v1"
    elif provider_choice == "openrouter":
        model = args.model or choose("OpenRouter model", "deepseek/deepseek-v4-pro")
        base_url = args.base_url or "https://openrouter.ai/api/v1"
    elif provider_choice == "custom":
        model = args.model or choose("Model name")
        base_url = args.base_url or choose("OpenAI-compatible base URL")
    else:
        print(f"Unsupported provider: {provider_choice}", file=sys.stderr)
        return 2

    provider, model, key_env = write_llm_config(provider_choice, model, base_url)

    api_key = args.api_key
    if not api_key and not args.skip_key:
        api_key = getpass.getpass(f"{key_env}: ").strip()
    if api_key:
        save_env_value(HOME / ".env", key_env, api_key)
    env_values = load_env_file(HOME / ".env")
    key_present = bool(os.environ.get(key_env) or env_values.get(key_env))

    print("Mender setup complete")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    print(f"Config: {HOME / 'config.yaml'}")
    print(f"Secrets: {HOME / '.env'}")
    if key_present:
        print(f"{key_env}: present")
    else:
        print(f"Key not saved. Add {key_env} to {HOME / '.env'} before online use.")
    return 0


def cmd_prelaunch(args: argparse.Namespace) -> int:
    ensure_mender_files()
    env_values = load_env_file(HOME / ".env")
    llm = llm_settings()
    if provider_key_present(llm, env_values):
        return 0

    print("Mender prelaunch")
    print("----------------")
    print(f"{llm['key_env']} is missing for provider '{llm['provider']}'.")
    print("Mender needs an LLM API key before starting the repair chat.")
    if args.no_prompt or not sys.stdin.isatty():
        print(f"Run setup first: mender setup   or add {llm['key_env']} to {HOME / '.env'}", file=sys.stderr)
        return 1

    selected = choose("Run setup now", "Y").strip().lower()
    if selected in ("y", "yes"):
        setup_args = argparse.Namespace(provider="", model="", base_url="", api_key="", skip_key=False)
        return cmd_setup(setup_args)
    print("Mender launch cancelled. Run setup when you are ready to add an API key.")
    return 1


def cmd_audit(args: argparse.Namespace) -> int:
    ensure_mender_files()
    sessions = read_jsonl(AUDIT_ROOT / "sessions.jsonl")
    if args.host:
        sessions = [s for s in sessions if s.get("host_id") == args.host or s.get("hostname") == args.host]
    sessions = sessions[-args.limit :]
    if args.json:
        print(json.dumps(sessions, indent=2, sort_keys=True))
        return 0
    print("Mender audit sessions")
    print("---------------------")
    if not sessions:
        print("No sessions recorded yet.")
        return 0
    for item in sessions:
        print(
            f"{item.get('ts', '')}  "
            f"{item.get('host_id', '')}  "
            f"{item.get('hostname', '')}  "
            f"{item.get('system', '')} {item.get('release', '')}  "
            f"{item.get('session_dir', '')}"
        )
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    ensure_mender_files()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_dir = AUDIT_ROOT / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"mender-logs-{stamp}.zip"
    manifest = {
        "created_at": now(),
        "mender_root": str(ROOT),
        "excluded": ["home/.env", "audit/bundles/*", "._*", ".DS_Store", "__MACOSX/*"],
        "note": "Bundle contains Mender audit/session/launcher logs and non-secret config files.",
    }
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("bundle-manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        add_bundle_path(bundle, AUDIT_ROOT)
        for rel in (
            "home/config.yaml",
            "home/SOUL.md",
            "home/MENDER_PERSONA.md",
            "README.md",
            "Mender.command",
            "Mender.desktop",
            "Mender.app/Contents/Info.plist",
            "Mender.app/Contents/MacOS/Mender",
            "Start-Mender.cmd",
            "mender",
            "mender.sh",
            "mender.cmd",
            "mender.ps1",
            "Start-Mender.ps1",
            "bootstrap.ps1",
            "bootstrap.sh",
            "update-hermes.sh",
            "update-mender.sh",
            "scripts/check-powershell.ps1",
            "scripts/smoke-test.sh",
            "scripts/static-check.py",
            "scripts/windows-smoke.ps1",
            "support/mender_boot.py",
        ):
            add_bundle_path(bundle, ROOT / rel)
    print(f"Mender log bundle: {bundle_path}")
    return 0


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
    note = sub.add_parser("note")
    note.add_argument("category")
    note.add_argument("detail", nargs="+")
    note.set_defaults(func=cmd_note)
    finish = sub.add_parser("finish")
    finish.set_defaults(func=cmd_finish)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
    ready = sub.add_parser("ready")
    ready.add_argument("--json", action="store_true")
    ready.set_defaults(func=cmd_ready)
    llm_check = sub.add_parser("llm-check", aliases=["chat-check"])
    llm_check.add_argument("--json", action="store_true")
    llm_check.add_argument("--prompt", default="")
    llm_check.add_argument("--expected", default="")
    llm_check.add_argument("--timeout", type=int, default=120)
    llm_check.set_defaults(func=cmd_llm_check)
    set_key = sub.add_parser("set-key")
    set_key.add_argument("--value", default="")
    set_key.add_argument("--env", default="")
    set_key.set_defaults(func=cmd_set_key)
    setup = sub.add_parser("setup")
    setup.add_argument("--provider", choices=("deepseek", "openrouter", "custom"), default="")
    setup.add_argument("--model", default="")
    setup.add_argument("--base-url", default="")
    setup.add_argument("--api-key", default="")
    setup.add_argument("--skip-key", action="store_true")
    setup.set_defaults(func=cmd_setup)
    prelaunch = sub.add_parser("prelaunch")
    prelaunch.add_argument("--no-prompt", action="store_true")
    prelaunch.set_defaults(func=cmd_prelaunch)
    audit = sub.add_parser("audit")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--host", default="")
    audit.add_argument("--limit", type=int, default=20)
    audit.set_defaults(func=cmd_audit)
    logs = sub.add_parser("logs")
    logs.set_defaults(func=cmd_logs)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
