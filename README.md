# Mender

Mender is a portable computer-repair agent built on [Hermes Agent](https://github.com/NousResearch/hermes-agent). Put this repo on a portable drive, choose an LLM provider, add an API key, and start a terminal repair session on a Mac, Linux, or Windows computer.

Mender keeps its config, sessions, and audit logs on the drive.

## What It Does

- Runs Hermes Agent from the portable drive.
- Uses DeepSeek V4 Pro through the direct DeepSeek API by default.
- Can be reconfigured during setup for OpenRouter or another OpenAI-compatible endpoint.
- Opens a terminal chat focused on diagnosing and repairing the connected computer.
- Writes startup inventory and session audit logs per host.
- Injects the current host/session startup prompt into Hermes before the chat starts.
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

Choose your LLM and save the API key locally on the drive:

```bash
bash mender.sh setup
```

DeepSeek direct is the default and uses `deepseek-v4-pro`. You can also run setup non-interactively:

```bash
bash mender.sh setup --provider deepseek
bash mender.sh setup --provider openrouter --model deepseek/deepseek-v4-pro
bash mender.sh setup --provider custom --model your-model --base-url https://your-provider.example/v1
```

Secrets stay in `home/.env` on the portable drive and are ignored by Git. You can also edit `home/.env` directly and set the provider-specific key, such as `DEEPSEEK_API_KEY=sk-your-key`.

Start Mender:

```bash
bash mender.sh
```

## Windows

Clone the repo onto the portable drive, then run PowerShell from the Mender folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1
.\mender.cmd setup
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
- `home/SOUL.md`: regenerated at launch from `home/MENDER_PERSONA.md` plus the active startup prompt so Hermes sees the current host context.
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
bash mender.sh update-hermes
```

Windows:

```powershell
.\mender.cmd update-hermes
```

`update-hermes` pulls the latest `NousResearch/hermes-agent` source and reinstalls the runtime while preserving Mender's `home/` config, secrets, sessions, and `audit/` logs. Installer scratch HOME is sandboxed under the connected computer's temp directory so update helpers avoid writing Hermes config into the connected computer's real user home and avoid ExFAT build-cache issues.

## Safety

Mender is a repair assistant, not an unattended malware-removal or disk-recovery appliance. Review commands before approving them, especially anything that changes disks, bootloaders, permissions, accounts, services, drivers, startup items, or security settings.
