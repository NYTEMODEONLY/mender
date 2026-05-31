# Mender

Mender is a portable computer-repair agent built on [Hermes Agent](https://github.com/NousResearch/hermes-agent). Put this repo on a portable drive, add a DeepSeek API key, and start a terminal repair session on a Mac, Linux, or Windows computer.

Mender keeps its config, sessions, and audit logs on the drive.

## What It Does

- Runs Hermes Agent from the portable drive.
- Uses DeepSeek V4 Pro through the direct DeepSeek API.
- Opens a terminal chat focused on diagnosing and repairing the connected computer.
- Writes startup inventory and session audit logs per host.
- Tags Hermes sessions as `mender` and enables Hermes checkpoints.
- Can update Hermes from Git while preserving Mender state.

## Quick Start On A Portable Drive

Clone this repo to the drive:

```bash
cd /Volumes/SLIM
git clone https://github.com/NYTEMODEONLY/mender.git Mender
cd Mender
bash bootstrap.sh
```

Add your API key:

```bash
bash mender.sh set-key
```

You can also edit `home/.env` directly and set `DEEPSEEK_API_KEY=sk-your-key`.

Start Mender:

```bash
bash mender.sh
```

## Windows

Clone the repo onto the portable drive, then run PowerShell from the Mender folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
notepad .\home\.env
.\mender.cmd
```

Or set the key from PowerShell after bootstrap:

```powershell
.\mender.cmd set-key
```

## Healthcheck

```bash
bash mender.sh doctor
bash mender.sh ready
```

Windows:

```powershell
.\mender.cmd doctor
.\mender.cmd ready
```

The latest report is written to:

```text
audit/doctor-latest.json
audit/ready-latest.json
```

## Audit Logs

Each run creates:

```text
audit/<host-id>/<timestamp>/
```

The session folder contains:

- `startup.json`: host profile, drive state, Hermes install state, network probe, and inventory.
- `startup_prompt.md`: the repair-session startup prompt and required opening sequence.
- `events.jsonl`: lifecycle events.
- `terminal.log`: terminal transcript when supported by the host.
- `manifest.json`: closeout hashes and file sizes.

Mender also keeps:

- `audit/sessions.jsonl`: append-only session index.
- `audit/hosts/<host-id>.json`: latest known profile for each connected host.

List recent sessions:

```bash
bash mender.sh audit
```

Windows:

```powershell
.\mender.cmd audit
```

## Update

```bash
bash update-mender.sh
```

Windows:

```powershell
cd .\hermes-agent
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -InstallDir ..\hermes-agent -HermesHome ..\home -SkipSetup
```

## Safety

Mender is a repair assistant, not an unattended malware-removal or disk-recovery appliance. Review commands before approving them, especially anything that changes disks, bootloaders, permissions, accounts, services, drivers, startup items, or security settings.
