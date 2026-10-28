param(
    [Parameter(Mandatory=$true)][string]$DotnetRoot,
    [Parameter(Mandatory=$true)][string]$ConnectionFile,
    [Parameter(Mandatory=$true)][string]$Godot
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:DOTNET_ROOT = (Resolve-Path -LiteralPath $DotnetRoot).Path
$env:PATH = $env:DOTNET_ROOT + ';' + $env:PATH
$env:FANTASYCARD_TEST_POSTGRES = (Get-Content -LiteralPath $ConnectionFile -Raw).Trim()
if ($env:FANTASYCARD_TEST_POSTGRES -notmatch '(?i)Host=(127\.0\.0\.1|localhost);') { throw 'QA requires an isolated loopback PostgreSQL database.' }
New-Item -ItemType Directory -Force "$repo/work" | Out-Null
Push-Location "$repo/server"
try {
    & "$env:DOTNET_ROOT/dotnet.exe" --version
    & "$env:DOTNET_ROOT/dotnet.exe" test FantasyCard.Server.slnx --artifacts-path .artifacts/qa-final --logger "trx;LogFilePrefix=qa-$run" --results-directory .artifacts/qa-final/results *> "$repo/work/qa-solution-$run.log"
    $solutionExit = $LASTEXITCODE
} finally { Pop-Location }
Push-Location $repo
try {
    python client/tests/run_http_protobuf_client.py --godot $Godot --work-dir "work/qa-client-$run" *> "work/qa-client-$run.log"
    $clientExit = $LASTEXITCODE
} finally { Pop-Location }
Write-Output "solution_exit=$solutionExit client_exit=$clientExit logs=$repo/work run=$run"
if ($solutionExit -ne 0 -or $clientExit -ne 0) { exit 1 }
