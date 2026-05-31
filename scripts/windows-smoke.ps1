$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:MENDER_SMOKE_FAST = "1"
$env:MENDER_SKIP_NETWORK_PROBE = "1"
$env:DEEPSEEK_API_KEY = "smoke-key"

function Step {
  param([string]$Name)
  Write-Host "mender windows smoke: $Name"
}

function Invoke-Python {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "python $($Arguments -join ' ') failed with exit $LASTEXITCODE"
  }
}

Step "static checks"
Invoke-Python "scripts/static-check.py"

Step "python syntax"
Invoke-Python "-m" "py_compile" "support/mender_boot.py" "scripts/static-check.py"

Step "powershell syntax"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-powershell.ps1
if ($LASTEXITCODE -ne 0) {
  throw "PowerShell syntax checks failed with exit $LASTEXITCODE"
}

Step "setup"
Invoke-Python "support/mender_boot.py" "setup" "--provider" "deepseek" "--model" "deepseek-v4-pro" "--skip-key"

Step "prelaunch"
Invoke-Python "support/mender_boot.py" "prelaunch" "--no-prompt"

Step "doctor"
Invoke-Python "support/mender_boot.py" "doctor" "--json"

Step "start"
Invoke-Python "support/mender_boot.py" "start" "--no-inventory"
$latestPath = Join-Path $Root "audit\latest-session.json"
if (!(Test-Path $latestPath)) {
  throw "audit/latest-session.json was not created"
}
$latest = Get-Content $latestPath -Raw | ConvertFrom-Json
foreach ($requiredPath in @($latest.startup_prompt, $latest.startup_json, $latest.active_soul)) {
  if (!(Test-Path $requiredPath)) {
    throw "Expected audit artifact missing: $requiredPath"
  }
}
if ((Get-Content $latest.startup_prompt -Raw) -notmatch "Required Opening Sequence") {
  throw "Startup prompt missing required opening sequence"
}
if ((Get-Content $latest.active_soul -Raw) -notmatch "Active Mender Repair Session") {
  throw "Active SOUL missing repair-session context"
}

Step "event and finish"
Invoke-Python "support/mender_boot.py" "event" "windows_smoke" "ok"
Invoke-Python "support/mender_boot.py" "finish"

Step "audit index"
Invoke-Python "support/mender_boot.py" "audit" "--json"

Step "windows launcher log bundle"
cmd /c Start-Mender.cmd logs
if ($LASTEXITCODE -ne 0) {
  throw "Start-Mender.cmd logs failed with exit $LASTEXITCODE"
}
$bundle = Get-ChildItem -Path (Join-Path $Root "audit\bundles") -Filter "mender-logs-*.zip" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if ($null -eq $bundle) {
  throw "Windows launcher did not create a log bundle"
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($bundle.FullName)
try {
  $entries = @($zip.Entries | ForEach-Object { $_.FullName -replace "\\", "/" })
} finally {
  $zip.Dispose()
}
if ($entries -match "(^|/)home/\.env$|sk-[A-Za-z0-9_-]{16,}") {
  throw "Windows log bundle appears to include a secret"
}
foreach ($entry in @("mender.cmd", "Start-Mender.cmd", "Start-Mender.ps1", "support/mender_boot.py")) {
  $leaf = Split-Path $entry -Leaf
  if (-not ($entries | Where-Object { (Split-Path $_ -Leaf) -eq $leaf })) {
    throw "Windows log bundle missing $entry"
  }
}

Write-Host "mender windows smoke tests passed"
