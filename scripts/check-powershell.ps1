$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scripts = @(
  (Join-Path $Root "bootstrap.ps1"),
  (Join-Path $Root "mender.ps1"),
  (Join-Path $Root "Start-Mender.ps1")
)

foreach ($script in $scripts) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors -and $errors.Count -gt 0) {
    Write-Error "PowerShell parse failed for $script"
    $errors | Format-List | Out-String | Write-Error
    exit 1
  }
}

$cmdPath = Join-Path $Root "mender.cmd"
$cmd = Get-Content $cmdPath -Raw
if ($cmd -notmatch "-NoProfile") {
  Write-Error "mender.cmd must launch PowerShell with -NoProfile"
  exit 1
}

$friendlyCmdPath = Join-Path $Root "Start-Mender.cmd"
$friendlyCmd = Get-Content $friendlyCmdPath -Raw
if ($friendlyCmd -notmatch "mender.cmd") {
  Write-Error "Start-Mender.cmd must delegate to mender.cmd"
  exit 1
}

Write-Host "mender PowerShell launcher checks passed"
