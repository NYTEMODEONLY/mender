#!/usr/bin/env python3
"""Repository-level checks for portable launchers."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    cmd = read("mender.cmd")
    friendly_cmd = read("Start-Mender.cmd")
    unix_mender = read("mender")
    friendly_command = read("Mender.command")
    linux_desktop = read("Mender.desktop")
    mac_app = read("Mender.app/Contents/MacOS/Mender")
    ps_mender = read("mender.ps1")
    start_ps = read("Start-Mender.ps1")
    bootstrap_ps = read("bootstrap.ps1")
    update_mender = read("update-mender.sh")
    update_hermes = read("update-hermes.sh")
    powershell_check = read("scripts/check-powershell.ps1")
    windows_smoke = read("scripts/windows-smoke.ps1")
    workflow = read(".github/workflows/smoke.yml")
    boot_py = read("support/mender_boot.py")

    require("-NoProfile" in cmd, "mender.cmd must launch PowerShell with -NoProfile")
    require("mender.cmd" in friendly_cmd, "Start-Mender.cmd must delegate to mender.cmd")
    require("mender.sh" in unix_mender, "extensionless mender launcher must delegate to mender.sh")
    require("mender" in friendly_command, "Mender.command must delegate to mender")
    require("./mender" in linux_desktop, "Mender.desktop must launch ./mender")
    require("./mender" in mac_app, "Mender.app must launch ./mender")
    require("Start-Mender.ps1" in ps_mender, "mender.ps1 must delegate to Start-Mender.ps1")
    require("update-hermes.sh" in read("mender.sh"), "mender.sh must route update-hermes to update-hermes.sh")
    require("update-mender.sh" in read("mender.sh"), "mender.sh must route update-mender to update-mender.sh")
    require("NYTEMODEONLY/mender" in update_mender, "Mender self-update must target the public Mender repo")
    require("NYTEMODEONLY/mender" in start_ps, "Windows self-update must target the public Mender repo")
    require("NousResearch/hermes-agent" in update_hermes, "Hermes update script must target Hermes Agent")
    require("home/" in update_mender and "audit/" in update_mender and "hermes-agent/" in update_mender, "Mender self-update must preserve local state")
    require("Invoke-MenderSelfUpdate" in start_ps, "Start-Mender.ps1 must implement Mender self-update")
    require("Parser]::ParseFile" in powershell_check, "PowerShell check must parse launcher files")
    require("windows-latest" in workflow, "CI must include a Windows launcher check")
    require("windows-smoke.ps1" in workflow, "CI must run the Windows smoke script")
    require("macos-latest" in workflow, "CI must include a macOS smoke check")
    for path, text in (("Start-Mender.ps1", start_ps), ("bootstrap.ps1", bootstrap_ps)):
        require("Invoke-HermesInstaller" in text, f"{path} must sandbox Hermes installer calls")
        require("-NoProfile" in text, f"{path} must launch nested PowerShell with -NoProfile")
        require("HERMES_GIT_BASH_PATH" in text, f"{path} must restore Hermes Git Bash user env")
        require("SetEnvironmentVariable(\"Path\", $oldUserPath, \"User\")" in text, f"{path} must restore user PATH")
        require("SetEnvironmentVariable(\"HERMES_HOME\", $oldHermesHome, \"User\")" in text, f"{path} must restore user HERMES_HOME")
        require("Start-Transcript" in text, f"{path} must write launcher transcripts")
        require("Write-MenderLauncherFailure" in text, f"{path} must persist launcher failures")
    require("New-MenderLogBundle" in start_ps, "Start-Mender.ps1 must expose Windows log bundles")
    require('if ($Mode -eq "logs") {\n  Stop-MenderTranscript\n  New-MenderLogBundle' in start_ps, "Start-Mender.ps1 must close transcripts before bundling logs")
    require("Start-Mender.cmd logs" in windows_smoke, "Windows smoke must exercise the .cmd log bundle path")
    require("Required Opening Sequence" in windows_smoke, "Windows smoke must verify startup prompt generation")
    require("scripts\\windows-smoke.ps1" in start_ps, "Windows log bundles must include the Windows smoke script")
    require("update-hermes.sh" in start_ps and '"update-hermes.sh"' in boot_py, "Log bundles must include update scripts")
    require('"scripts/windows-smoke.ps1"' in boot_py, "Python log bundles must include the Windows smoke script")
    require("logs)" in read("mender.sh"), "mender.sh must expose log bundles")
    require("cmd_logs" in boot_py, "mender_boot.py must implement log bundles")
    require("cmd_note" in boot_py, "mender_boot.py must implement structured repair notes")
    require("notes_jsonl" in boot_py, "Mender sessions must include a repair notes log")
    require("note)" in read("mender.sh"), "mender.sh must expose repair notes")
    require('$Mode -eq "note"' in start_ps, "Start-Mender.ps1 must expose repair notes")
    require("windows smoke note ok" in windows_smoke, "Windows smoke must verify repair notes")
    require("cmd_prelaunch" in boot_py, "mender_boot.py must implement prelaunch setup gating")
    require("prelaunch" in read("mender.sh"), "mender.sh must run prelaunch before Hermes chat")
    require('"prelaunch"' in start_ps, "Start-Mender.ps1 must run prelaunch before Hermes chat")
    require("Import-MenderEnv" in start_ps, "Start-Mender.ps1 must reload env after interactive setup")

    require("Get-CimInstance Win32_DiskDrive" in boot_py, "Windows inventory must include modern disk CIM checks")
    require("Get-ComputerInfo" in boot_py, "Windows inventory must include modern OS/hardware checks")
    require("Get-NetIPConfiguration" in boot_py, "Windows inventory must include modern network checks")

    tracked_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in ROOT.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and "home" not in p.parts
        and "audit" not in p.parts
        and "hermes-agent" not in p.parts
        and "runtime" not in p.parts
    )
    require(not re.search(r"sk-[A-Za-z0-9]{16,}", tracked_text), "possible API key found in tracked project files")
    print("mender static checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
