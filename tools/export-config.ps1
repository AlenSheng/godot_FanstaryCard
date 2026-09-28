param(
    [string]$InputWorkbook = "config/FantasyCard_Config.xlsx",
    [string]$ConfigVersion = "gdd-0.70-numerical-1",
    [string]$PythonExecutable = "python"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repoRoot "server")
try {
    dotnet run --project tools/FantasyCard.ConfigExporter -- `
        --input (Join-Path $repoRoot $InputWorkbook) `
        --version $ConfigVersion `
        --server-output (Join-Path $repoRoot "server/config/generated") `
        --client-output (Join-Path $repoRoot "client/data/generated")
    if ($LASTEXITCODE -ne 0) { throw "Config export failed with exit code $LASTEXITCODE" }
    & $PythonExecutable (Join-Path $repoRoot "tools/export_client_catalog.py")
    if ($LASTEXITCODE -ne 0) { throw "Godot catalog export failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
