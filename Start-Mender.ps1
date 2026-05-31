$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:MENDER_ROOT = $Root
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$env:UV_LINK_MODE = "copy"

$Mode = if ($args.Count -gt 0) { $args[0] } else { "start" }

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

if (!(Test-Path $HermesExe)) {
  if (!(Test-Path (Join-Path $env:HERMES_INSTALL_DIR ".git"))) {
    Write-Host "Hermes Agent source is missing. Cloning NousResearch/hermes-agent..."
    if (Test-Path $env:HERMES_INSTALL_DIR) {
      Remove-Item -Recurse -Force $env:HERMES_INSTALL_DIR
    }
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git $env:HERMES_INSTALL_DIR
  }
  Write-Host "Hermes runtime is missing. Installing/updating on this computer..."
  & powershell -ExecutionPolicy Bypass -File (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1") -InstallDir $env:HERMES_INSTALL_DIR -HermesHome $env:HERMES_HOME -SkipSetup
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
  & $PythonExe (Join-Path $Root "support\mender_boot.py") set-key
  exit $LASTEXITCODE
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
