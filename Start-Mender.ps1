$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:MENDER_ROOT = $Root
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$env:UV_LINK_MODE = "copy"
$env:PYTHONDONTWRITEBYTECODE = "1"
$MenderUserProfile = Join-Path $Root "runtime\userprofile"
$MenderLocalAppData = Join-Path $Root "runtime\localappdata"

$Mode = if ($args.Count -gt 0) { $args[0] } else { "start" }

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

$EnvFile = Join-Path $env:HERMES_HOME ".env"
if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
    $parts = $_ -split "=", 2
    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
  }
}

$HermesExe = Join-Path $env:HERMES_INSTALL_DIR "venv\Scripts\hermes.exe"
$PythonExe = Join-Path $env:HERMES_INSTALL_DIR "venv\Scripts\python.exe"

if ($Mode -eq "update" -or $Mode -eq "update-hermes") {
  if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
    if (Test-Path $env:HERMES_INSTALL_DIR) {
      Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
    }
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git $env:HERMES_INSTALL_DIR
  }
  git -C $env:HERMES_INSTALL_DIR pull --ff-only origin main
  Invoke-HermesInstaller (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1")
  Write-Host "Hermes Agent updated for Mender."
  exit 0
}

if (!(Test-Path $HermesExe)) {
  if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
    Write-Host "Hermes Agent source is missing. Cloning NousResearch/hermes-agent..."
    if (Test-Path $env:HERMES_INSTALL_DIR) {
      Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
    }
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git $env:HERMES_INSTALL_DIR
  }
  Write-Host "Hermes runtime is missing. Installing/updating on this computer..."
  Invoke-HermesInstaller (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1")
}

if ($Mode -eq "doctor") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") doctor
  exit $LASTEXITCODE
}
if ($Mode -eq "doctor-json") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") doctor --json
  exit $LASTEXITCODE
}
if ($Mode -eq "ready") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") ready
  exit $LASTEXITCODE
}
if ($Mode -eq "set-key") {
  $keyArgs = @("set-key")
  if ($args.Count -gt 1) {
    $keyArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @keyArgs
  exit $LASTEXITCODE
}
if ($Mode -eq "setup") {
  $setupArgs = @("setup")
  if ($args.Count -gt 1) {
    $setupArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @setupArgs
  exit $LASTEXITCODE
}
if ($Mode -eq "audit") {
  $auditArgs = @("audit")
  if ($args.Count -gt 1) {
    $auditArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @auditArgs
  exit $LASTEXITCODE
}
if ($Mode -ne "start" -and $Mode -ne "") {
  Write-Host "Usage: .\mender.cmd [start|setup|doctor|doctor-json|ready|set-key|audit|update|update-hermes]"
  exit 2
}

& $PythonExe (Join-Path $Root "support\mender_boot.py") start
& $PythonExe (Join-Path $Root "support\mender_boot.py") event hermes_launch "starting Hermes chat"

$latestPath = Join-Path $Root "audit\latest-session.json"
$latest = Get-Content $latestPath -Raw | ConvertFrom-Json
try {
  Start-Transcript -Path $latest.terminal_log -Append | Out-Null
} catch {
  Write-Host "PowerShell transcript unavailable; Hermes native logs still apply."
}
& $HermesExe chat --source mender --checkpoints
$exitCode = $LASTEXITCODE
try { Stop-Transcript | Out-Null } catch {}
& $PythonExe (Join-Path $Root "support\mender_boot.py") event hermes_exit "exit=$exitCode"
& $PythonExe (Join-Path $Root "support\mender_boot.py") finish
exit $exitCode
