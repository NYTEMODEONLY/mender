$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $Root "Start-Mender.ps1") @args
exit $LASTEXITCODE
