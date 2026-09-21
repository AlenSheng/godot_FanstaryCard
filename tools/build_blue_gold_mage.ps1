param(
    [string]$BlenderPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BlenderPath)) {
    $candidate = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($null -ne $candidate) { $BlenderPath = $candidate.Source }
}
if ([string]::IsNullOrWhiteSpace($BlenderPath)) {
    $candidates = @(
        "G:\Program Files\Blender 5.2\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender\blender.exe",
        "$env:LOCALAPPDATA\Blender Foundation\Blender\blender.exe"
    )
    $known = @($candidates | Where-Object { Test-Path -LiteralPath $_ })
    if ($known.Count -gt 0) { $BlenderPath = $known[0] }
}
if ([string]::IsNullOrWhiteSpace($BlenderPath) -or -not (Test-Path -LiteralPath $BlenderPath)) {
    throw "Blender executable not found. Install Blender or rerun with -BlenderPath 'C:\path\to\blender.exe'."
}

& $BlenderPath --background --python (Join-Path $projectRoot "tools\generate_blue_gold_mage.py") 2>&1 | Tee-Object -Variable buildOutput
if ($LASTEXITCODE -ne 0) { throw "Blender character build failed with exit code $LASTEXITCODE." }
if (-not ($buildOutput -match "ASSET_REPORT")) { throw "Blender exited without producing a validated character asset report." }
