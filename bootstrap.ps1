$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$env:UV_LINK_MODE = "copy"
$env:PYTHONDONTWRITEBYTECODE = "1"
$MenderUserProfile = Join-Path $Root "runtime\userprofile"
$MenderLocalAppData = Join-Path $Root "runtime\localappdata"

New-Item -ItemType Directory -Force -Path $env:HERMES_HOME | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "audit") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null
New-Item -ItemType Directory -Force -Path $MenderUserProfile | Out-Null
New-Item -ItemType Directory -Force -Path $MenderLocalAppData | Out-Null

function Invoke-HermesInstaller {
  param([string]$InstallerPath)

  $oldUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $oldHermesHome = [Environment]::GetEnvironmentVariable("HERMES_HOME", "User")
  $oldUserProfile = $env:USERPROFILE
  $oldLocalAppData = $env:LOCALAPPDATA
  try {
    $env:USERPROFILE = $MenderUserProfile
    $env:LOCALAPPDATA = $MenderLocalAppData
    & powershell -ExecutionPolicy Bypass -File $InstallerPath -InstallDir $env:HERMES_INSTALL_DIR -HermesHome $env:HERMES_HOME -SkipSetup
  } finally {
    $env:USERPROFILE = $oldUserProfile
    $env:LOCALAPPDATA = $oldLocalAppData
    [Environment]::SetEnvironmentVariable("Path", $oldUserPath, "User")
    [Environment]::SetEnvironmentVariable("HERMES_HOME", $oldHermesHome, "User")
  }
}

if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
  if (Test-Path $env:HERMES_INSTALL_DIR) {
    Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
  }
  git clone --depth 1 https://github.com/NousResearch/hermes-agent.git $env:HERMES_INSTALL_DIR
}

if (!(Test-Path (Join-Path $env:HERMES_HOME ".env"))) {
  Copy-Item (Join-Path $Root "templates\.env.example") (Join-Path $env:HERMES_HOME ".env")
}
if (!(Test-Path (Join-Path $env:HERMES_HOME "config.yaml"))) {
  Copy-Item (Join-Path $Root "templates\config.yaml") (Join-Path $env:HERMES_HOME "config.yaml")
}
if (!(Test-Path (Join-Path $env:HERMES_HOME "SOUL.md"))) {
  Copy-Item (Join-Path $Root "templates\SOUL.md") (Join-Path $env:HERMES_HOME "SOUL.md")
}

Invoke-HermesInstaller (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1")

Write-Host "Mender bootstrap complete. Run .\mender.cmd setup"
