$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:HERMES_HOME = Join-Path $Root "home"
$env:HERMES_INSTALL_DIR = Join-Path $Root "hermes-agent"
$env:UV_LINK_MODE = "copy"
$env:PYTHONDONTWRITEBYTECODE = "1"

New-Item -ItemType Directory -Force -Path $env:HERMES_HOME | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "audit") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null

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

powershell -ExecutionPolicy Bypass -File (Join-Path $env:HERMES_INSTALL_DIR "scripts\install.ps1") -InstallDir $env:HERMES_INSTALL_DIR -HermesHome $env:HERMES_HOME -SkipSetup

Write-Host "Mender bootstrap complete. Add DEEPSEEK_API_KEY to home\.env, then run .\mender.cmd"
