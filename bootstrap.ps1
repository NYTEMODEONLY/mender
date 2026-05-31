$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$MenderRuntime = Join-Path $Root "runtime"
$env:UV_LINK_MODE = "copy"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $MenderRuntime "uv\python"
$env:UV_PYTHON_BIN_DIR = Join-Path $MenderRuntime "uv\bin"
$env:UV_CACHE_DIR = Join-Path $MenderRuntime "uv\cache"
$env:UV_TOOL_DIR = Join-Path $MenderRuntime "uv\tools"
$env:PYTHONDONTWRITEBYTECODE = "1"
$MenderInstallScratch = Join-Path ([System.IO.Path]::GetTempPath()) "mender-install-home"
$MenderUserProfile = Join-Path $MenderInstallScratch "userprofile"
$MenderLocalAppData = Join-Path $MenderInstallScratch "localappdata"
$AuditRoot = Join-Path $Root "audit"
$LauncherLogDir = Join-Path $AuditRoot "launcher"
$LauncherStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LauncherLog = Join-Path $LauncherLogDir "windows-bootstrap-$LauncherStamp.log"
$LatestLauncherError = Join-Path $LauncherLogDir "latest-windows-bootstrap-error.txt"
$script:TranscriptStarted = $false

New-Item -ItemType Directory -Force -Path $env:HERMES_HOME | Out-Null
New-Item -ItemType Directory -Force -Path $AuditRoot | Out-Null
New-Item -ItemType Directory -Force -Path $LauncherLogDir | Out-Null
New-Item -ItemType Directory -Force -Path $MenderRuntime | Out-Null
New-Item -ItemType Directory -Force -Path $MenderUserProfile | Out-Null
New-Item -ItemType Directory -Force -Path $MenderLocalAppData | Out-Null
try {
  Start-Transcript -Path $LauncherLog -Append | Out-Null
  $script:TranscriptStarted = $true
} catch {
  Write-Host "Mender bootstrap transcript unavailable: $($_.Exception.Message)"
}

function Stop-MenderTranscript {
  if ($script:TranscriptStarted) {
    try { Stop-Transcript | Out-Null } catch {}
    $script:TranscriptStarted = $false
  }
}

function Write-MenderLauncherFailure {
  param($ErrorRecord)

  $message = @"
Mender Windows bootstrap failure
Time: $(Get-Date -Format o)
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

if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
  if (Test-Path $env:HERMES_INSTALL_DIR) {
    Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
  }
  Invoke-Checked git "clone" "--depth" "1" "https://github.com/NousResearch/hermes-agent.git" $env:HERMES_INSTALL_DIR
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
Exit-Mender 0
