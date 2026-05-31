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
    start_ps = read("Start-Mender.ps1")
    bootstrap_ps = read("bootstrap.ps1")
    powershell_check = read("scripts/check-powershell.ps1")
    workflow = read(".github/workflows/smoke.yml")
    boot_py = read("support/mender_boot.py")

    require("-NoProfile" in cmd, "mender.cmd must launch PowerShell with -NoProfile")
    require("Parser]::ParseFile" in powershell_check, "PowerShell check must parse launcher files")
    require("windows-latest" in workflow, "CI must include a Windows launcher check")
    require("macos-latest" in workflow, "CI must include a macOS smoke check")
    for path, text in (("Start-Mender.ps1", start_ps), ("bootstrap.ps1", bootstrap_ps)):
        require("Invoke-HermesInstaller" in text, f"{path} must sandbox Hermes installer calls")
        require("-NoProfile" in text, f"{path} must launch nested PowerShell with -NoProfile")
        require("HERMES_GIT_BASH_PATH" in text, f"{path} must restore Hermes Git Bash user env")
        require("SetEnvironmentVariable(\"Path\", $oldUserPath, \"User\")" in text, f"{path} must restore user PATH")
        require("SetEnvironmentVariable(\"HERMES_HOME\", $oldHermesHome, \"User\")" in text, f"{path} must restore user HERMES_HOME")

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
