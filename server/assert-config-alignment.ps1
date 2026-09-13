param(
    [string]$RunningUrl
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'config-alignment.ps1')

try {
    $published = Assert-PublishedConfigAlignment
    if (-not [string]::IsNullOrWhiteSpace($RunningUrl)) {
        Assert-RunningConfigAlignment $RunningUrl $published
    }
    exit 0
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    if ($_.Exception.Message -match 'does not match client') { exit 1 }
    exit 2
}
