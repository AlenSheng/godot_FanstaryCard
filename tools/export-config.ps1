param(
    [string]$InputWorkbook = "config/FantasyCard_Config.xlsx",
    [string]$ConfigVersion = "gdd-0.64-config-1"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repoRoot "server")
try {
    dotnet run --project tools/FantasyCard.ConfigExporter -- `
        --input (Join-Path $repoRoot $InputWorkbook) `
        --version $ConfigVersion `
        --server-output (Join-Path $repoRoot "server/config/generated") `
        --client-output (Join-Path $repoRoot "FantasyCard_Unity/New Tuanjie Project/Assets/StreamingAssets/Config")
    if ($LASTEXITCODE -ne 0) { throw "Config export failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }