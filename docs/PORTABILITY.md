# Mender Portability Notes

Mender keeps source, configuration, secrets, sessions, and audit data on the USB drive.

Hermes Agent itself requires Python 3.11 and installs dependencies into a virtual environment. On a new computer, the startup script can provision what Hermes needs using the bundled Hermes installer and an internet connection.

Because this drive is ExFAT for Mac/Windows compatibility, some Python and package-manager operations cannot use POSIX symlinks or hardlinks. The launchers set `UV_LINK_MODE=copy` to favor copy-based installs on the drive.

The target computer must have:

- internet access for first-run dependency setup and DeepSeek API calls
- permission to run shell or PowerShell scripts
- Python/uv bootstrapping allowed by the host security policy

On a fresh Windows host, double-click `Start-Mender.cmd` or run `mender.cmd`. The PowerShell launcher uses the bundled Hermes Windows installer in `hermes-agent/scripts/install.ps1` to create the host-specific Windows virtual environment on the drive.

On macOS/Linux, run `bash mender.sh`. The shell launcher uses the Hermes installer in `hermes-agent/scripts/install.sh` if the runtime is missing.

Before Hermes opens, Mender runs a prelaunch check. If the configured provider's API key is missing, the launcher prompts for setup instead of starting a broken chat session. The key is saved only in `home/.env` on the drive.

Use `update-mender` to refresh Mender's launchers and helper scripts from `NYTEMODEONLY/mender` while preserving `home/`, `audit/`, `hermes-agent/`, and `runtime/`. Use `update-hermes` to refresh only the Hermes Agent runtime.

No repair command should be treated as safe just because Mender proposed it. Review and approve repair steps deliberately.
