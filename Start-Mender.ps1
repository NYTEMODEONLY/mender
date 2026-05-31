$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:MENDER_ROOT = $Root
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$env:UV_LINK_MODE = "copy"
$env:PYTHONDONTWRITEBYTECODE = "1"
$MenderInstallScratch = Join-Path ([System.IO.Path]::GetTempPath()) "mender-install-home"
$MenderUserProfile = Join-Path $MenderInstallScratch "userprofile"
$MenderLocalAppData = Join-Path $MenderInstallScratch "localappdata"

$Mode = if ($args.Count -gt 0) { $args[0] } else { "start" }
$AuditRoot = Join-Path $Root "audit"
$LauncherLogDir = Join-Path $AuditRoot "launcher"
$LauncherStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LauncherLog = Join-Path $LauncherLogDir "windows-$LauncherStamp.log"
$LatestLauncherError = Join-Path $LauncherLogDir "latest-windows-error.txt"
$script:TranscriptStarted = $false

New-Item -ItemType Directory -Force -Path $LauncherLogDir | Out-Null
try {
  Start-Transcript -Path $LauncherLog -Append | Out-Null
  $script:TranscriptStarted = $true
} catch {
  Write-Host "Mender launcher transcript unavailable: $($_.Exception.Message)"
}

New-Item -ItemType Directory -Force -Path $MenderUserProfile | Out-Null
New-Item -ItemType Directory -Force -Path $MenderLocalAppData | Out-Null

function Stop-MenderTranscript {
  if ($script:TranscriptStarted) {
    try { Stop-Transcript | Out-Null } catch {}
    $script:TranscriptStarted = $false
  }
}

function Write-MenderLauncherFailure {
  param($ErrorRecord)

  $message = @"
Mender Windows launcher failure
Time: $(Get-Date -Format o)
Mode: $Mode
Root: $Root
Log: $LauncherLog

$($ErrorRecord | Out-String)
"@
  Set-Content -Path $LatestLauncherError -Value $message -Encoding UTF8
  Write-Host $message
}

function Exit-Mender {
  param([int]$Code)

  Stop-MenderTranscript
  exit $Code
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
  )

  & $FilePath @Arguments
  $code = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  if ($code -ne 0) {
    throw "Command failed with exit $code`: $FilePath $($Arguments -join ' ')"
  }
}

function New-MenderLogBundle {
  $bundleDir = Join-Path $AuditRoot "bundles"
  New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null
  $bundlePath = Join-Path $bundleDir "mender-logs-$LauncherStamp.zip"
  $tempBundlePath = Join-Path ([System.IO.Path]::GetTempPath()) "mender-logs-$LauncherStamp.zip"
  $items = @()
  if (Test-Path $AuditRoot) {
    $items += Get-ChildItem -Path $AuditRoot -Recurse -File |
      Where-Object { $_.FullName -notlike "$bundleDir*" } |
      Select-Object -ExpandProperty FullName
  }
  foreach ($candidate in @(
    (Join-Path $env:HERMES_HOME "config.yaml"),
    (Join-Path $env:HERMES_HOME "SOUL.md"),
    (Join-Path $env:HERMES_HOME "MENDER_PERSONA.md"),
    (Join-Path $Root "README.md"),
    (Join-Path $Root "Mender.command"),
    (Join-Path $Root "Mender.desktop"),
    (Join-Path $Root "Start-Mender.cmd"),
    (Join-Path $Root "mender"),
    (Join-Path $Root "mender.cmd"),
    (Join-Path $Root "mender.ps1"),
    (Join-Path $Root "Start-Mender.ps1"),
    (Join-Path $Root "bootstrap.ps1"),
    (Join-Path $Root "scripts\check-powershell.ps1"),
    (Join-Path $Root "scripts\smoke-test.sh"),
    (Join-Path $Root "scripts\static-check.py"),
    (Join-Path $Root "scripts\windows-smoke.ps1"),
    (Join-Path $Root "support\mender_boot.py")
  )) {
    if (Test-Path $candidate) {
      $items += $candidate
    }
  }
  if (Test-Path $bundlePath) {
    Remove-Item -Force $bundlePath
  }
  if (Test-Path $tempBundlePath) {
    Remove-Item -Force $tempBundlePath
  }
  Compress-Archive -Path $items -DestinationPath $tempBundlePath -Force
  Move-Item -Force $tempBundlePath $bundlePath
  Write-Host "Mender log bundle: $bundlePath"
}

trap {
  Write-MenderLauncherFailure $_
  Stop-MenderTranscript
  exit 1
}

function Invoke-HermesInstaller {
  param([string]$InstallerPath)

  $oldUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $oldHermesHome = [Environment]::GetEnvironmentVariable("HERMES_HOME", "User")
  $oldHermesGitBashPath = [Environment]::GetEnvironmentVariable("HERMES_GIT_BASH_PATH", "User")
  $oldUserProfile = $env:USERPROFILE
  $oldLocalAppData = $env:LOCALAPPDATA
  try {
    $env:USERPROFILE = $MenderUserProfile
    $env:LOCALAPPDATA = $MenderLocalAppData
    Invoke-Checked powershell "-NoProfile" "-ExecutionPolicy" "Bypass" "-File" $InstallerPath "-InstallDir" $env:HERMES_INSTALL_DIR "-HermesHome" $env:HERMES_HOME "-SkipSetup"
  } finally {
    $env:USERPROFILE = $oldUserProfile
    $env:LOCALAPPDATA = $oldLocalAppData
    [Environment]::SetEnvironmentVariable("Path", $oldUserPath, "User")
    [Environment]::SetEnvironmentVariable("HERMES_HOME", $oldHermesHome, "User")
    [Environment]::SetEnvironmentVariable("HERMES_GIT_BASH_PATH", $oldHermesGitBashPath, "User")
  }
}

$EnvFile = Join-Path $env:HERMES_HOME ".env"
function Import-MenderEnv {
  if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
      if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
      $parts = $_ -split "=", 2
      $name = $parts[0].Trim()
      if ($name.StartsWith("export ")) {
        $name = $name.Substring(7).Trim()
      }
      if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
        [Environment]::SetEnvironmentVariable($name, $parts[1].Trim(), "Process")
      }
    }
  }
}
Import-MenderEnv

$HermesExe = Join-Path $env:HERMES_INSTALL_DIR "venv\Scripts\hermes.exe"
$PythonExe = Join-Path $env:HERMES_INSTALL_DIR "venv\Scripts\python.exe"

if ($Mode -eq "update" -or $Mode -eq "update-hermes") {
  if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
    if (Test-Path $env:HERMES_INSTALL_DIR) {
      Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
    }
    Invoke-Checked git "clone" "--depth" "1" "https://github.com/NousResearch/hermes-agent.git" $env:HERMES_INSTALL_DIR
  }
  Invoke-Checked git "-C" $env:HERMES_INSTALL_DIR "pull" "--ff-only" "origin" "main"
  Invoke-HermesInstaller (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1")
  Write-Host "Hermes Agent updated for Mender."
  Exit-Mender 0
}

if ($Mode -eq "logs") {
  Stop-MenderTranscript
  New-MenderLogBundle
  Exit-Mender 0
}

if (!(Test-Path $HermesExe)) {
  if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
    Write-Host "Hermes Agent source is missing. Cloning NousResearch/hermes-agent..."
    if (Test-Path $env:HERMES_INSTALL_DIR) {
      Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
    }
    Invoke-Checked git "clone" "--depth" "1" "https://github.com/NousResearch/hermes-agent.git" $env:HERMES_INSTALL_DIR
  }
  Write-Host "Hermes runtime is missing. Installing/updating on this computer..."
  Invoke-HermesInstaller (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1")
}

if ($Mode -eq "doctor") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") doctor
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "doctor-json") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") doctor --json
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "ready") {
  & $PythonExe (Join-Path $Root "support\mender_boot.py") ready
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "set-key") {
  $keyArgs = @("set-key")
  if ($args.Count -gt 1) {
    $keyArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @keyArgs
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "setup") {
  $setupArgs = @("setup")
  if ($args.Count -gt 1) {
    $setupArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @setupArgs
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "audit") {
  $auditArgs = @("audit")
  if ($args.Count -gt 1) {
    $auditArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @auditArgs
  Exit-Mender $LASTEXITCODE
}
if ($Mode -eq "note") {
  $noteArgs = @("note")
  if ($args.Count -gt 1) {
    $noteArgs += $args[1..($args.Count - 1)]
  }
  & $PythonExe (Join-Path $Root "support\mender_boot.py") @noteArgs
  Exit-Mender $LASTEXITCODE
}
if ($Mode -ne "start" -and $Mode -ne "") {
  Write-Host "Usage: .\mender.cmd [start|setup|doctor|doctor-json|ready|set-key|audit|note|logs|update|update-hermes]"
  Exit-Mender 2
}

Invoke-Checked $PythonExe (Join-Path $Root "support\mender_boot.py") "prelaunch"
Import-MenderEnv
Invoke-Checked $PythonExe (Join-Path $Root "support\mender_boot.py") "start"
Invoke-Checked $PythonExe (Join-Path $Root "support\mender_boot.py") "event" "hermes_launch" "starting Hermes chat"

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
Invoke-Checked $PythonExe (Join-Path $Root "support\mender_boot.py") "event" "hermes_exit" "exit=$exitCode"
Invoke-Checked $PythonExe (Join-Path $Root "support\mender_boot.py") "finish"
Exit-Mender $exitCode
