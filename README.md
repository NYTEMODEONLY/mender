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
- Can update Hermes and Mender itself while preserving drive-local state.

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
./mender
```

If the selected provider's API key is missing, Mender pauses before launching Hermes and offers to run setup in the same terminal. The saved key stays in `home/.env` on the portable drive.

On macOS/Linux, shells normally require `./mender` for a command in the current folder. If you add the Mender folder to `PATH`, `mender` works as a bare command.

Double-click launchers are also included in the drive root:

- macOS Finder: `Mender.app` or `Mender.command`
- Windows Explorer / Command Prompt: `Start-Mender.cmd` or `mender.cmd`
- Linux file managers: `Mender.desktop`

## Windows

Clone the repo onto the portable drive, then run PowerShell from the Mender folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1
.\mender.cmd setup
.\mender.cmd
```

In Command Prompt, `mender` also resolves to `mender.cmd` when you are in the Mender folder. PowerShell requires the explicit `.\` prefix for local commands, such as `.\mender.cmd` or `.\mender.ps1`.

Or set the key from PowerShell after bootstrap:

```powershell
.\mender.cmd set-key
```

The project CI runs a Windows smoke test that exercises setup, prelaunch, audit creation, event logging, session finish, and `Start-Mender.cmd logs` on `windows-latest`. A real USB run on a physical Windows computer is still the final portability proof.

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

Check that Hermes can reach the configured LLM and produce a one-shot response:

```bash
./mender chat-check
```

Windows:

```powershell
.\mender.cmd chat-check
```

The latest reports are written to:

```text
audit/doctor-latest.json
audit/ready-latest.json
audit/llm-check-latest.json
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
- `notes.jsonl`: structured repair notes for symptoms, diagnoses, commands, changes, risks, rollback plans, and verification.
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

Add a structured repair note to the active session:

```bash
./mender note verification "Wi-Fi reconnects successfully after renewing DHCP lease"
```

Windows:

```powershell
.\mender.cmd note verification "Wi-Fi reconnects successfully after renewing DHCP lease"
```

Collect a shareable troubleshooting bundle:

```bash
bash mender.sh logs
```

Windows:

```powershell
.\mender.cmd logs
```

Bundles are written under `audit/bundles/` and intentionally exclude `home/.env`. Windows bootstrap/startup failures are also transcribed under `audit/launcher/`, including failures that happen before Hermes is able to start.

## Update

Update Mender's own launcher/helper files from the public project while preserving `home/`, `audit/`, `hermes-agent/`, and `runtime/`:

```bash
bash mender.sh update-mender
```

Windows:

```powershell
.\mender.cmd update-mender
```

Update Hermes Agent:

```bash
bash mender.sh update-hermes
```

Windows:

```powershell
.\mender.cmd update-hermes
```

`update-hermes` pulls the latest `NousResearch/hermes-agent` source and reinstalls the runtime while preserving Mender's `home/` config, secrets, sessions, and `audit/` logs. Installer scratch HOME, uv's managed Python store, and transient build caches are sandboxed under the connected computer's temp directory. If a copied drive contains a stale venv from another host, Mender detects it and reinstalls the host runtime automatically.

`update-mender` pulls from `NYTEMODEONLY/mender` when the drive has a Git checkout. If Mender was copied onto the drive without `.git`, it falls back to the GitHub release archive and overlays only project files, leaving local secrets, audit data, and Hermes runtime untouched.

## Safety

Mender is a repair assistant, not an unattended malware-removal or disk-recovery appliance. Review commands before approving them, especially anything that changes disks, bootloaders, permissions, accounts, services, drivers, startup items, or security settings.
