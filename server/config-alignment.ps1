# Shared local-start helpers. Keep server/client published config identical, and
# refuse to leave a running process that still advertises an older configVersion.

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Read-TrimmedText([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) {
        throw "Missing published config file: $Path"
    }
    return (Get-Content -LiteralPath $Path -Raw).Trim()
}

function Get-PublishedConfigIdentity {
    $repoRoot = Get-RepoRoot
    $serverGenerated = Join-Path $PSScriptRoot 'config/generated'
    $clientGenerated = Join-Path $repoRoot 'client/data/generated'
    $catalogPath = Join-Path $repoRoot 'client/data/catalog.json'
    $serverBytes = Join-Path $serverGenerated 'fantasycard.config.bytes'
    $clientBytes = Join-Path $clientGenerated 'fantasycard.config.bytes'
    $serverVersion = Read-TrimmedText (Join-Path $serverGenerated 'fantasycard.config.version.txt')
    $clientVersion = Read-TrimmedText (Join-Path $clientGenerated 'fantasycard.config.version.txt')
    $serverHash = Read-TrimmedText (Join-Path $serverGenerated 'fantasycard.config.sha256')
    $clientHash = Read-TrimmedText (Join-Path $clientGenerated 'fantasycard.config.sha256')
    if (!(Test-Path -LiteralPath $catalogPath)) {
        throw "Missing client catalog: $catalogPath"
    }
    $catalog = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $catalogVersion = [string]$catalog.version
    if ([string]::IsNullOrWhiteSpace($serverVersion)) {
        throw 'Published server config version is empty.'
    }
    if ($serverVersion -ne $clientVersion -or $serverVersion -ne $catalogVersion) {
        throw @"
Published config versions are not aligned.
  server generated: $serverVersion
  client generated: $clientVersion
  client catalog:   $catalogVersion
Run tools/export-config.ps1 from the repository root, then start again.
"@
    }
    if ($serverHash -ne $clientHash) {
        throw "Published config hashes differ (server $serverHash, client $clientHash). Run tools/export-config.ps1."
    }
    if (!(Test-Path -LiteralPath $serverBytes) -or !(Test-Path -LiteralPath $clientBytes)) {
        throw 'Published config bytes are missing. Run tools/export-config.ps1.'
    }
    $serverData = [IO.File]::ReadAllBytes($serverBytes)
    $clientData = [IO.File]::ReadAllBytes($clientBytes)
    if ($serverData.Length -ne $clientData.Length -or
        [Convert]::ToBase64String($serverData) -ne [Convert]::ToBase64String($clientData)) {
        throw 'Published server/client config bytes differ. Run tools/export-config.ps1.'
    }
    return [pscustomobject]@{
        Version = $serverVersion
        Sha256 = $serverHash
    }
}

function Get-ServiceRootUrl([string]$Url) {
    $normalized = $Url.Trim()
    if ($normalized.EndsWith('/health/ready', [StringComparison]::OrdinalIgnoreCase)) {
        return $normalized.Substring(0, $normalized.Length - '/health/ready'.Length).TrimEnd('/') + '/'
    }
    $uri = [Uri]$normalized
    return $uri.GetLeftPart([UriPartial]::Authority) + '/'
}

function Get-RunningConfigVersion([string]$Url) {
    $root = Get-ServiceRootUrl $Url
    try {
        $info = Invoke-RestMethod -UseBasicParsing -Uri $root -TimeoutSec 3
    } catch {
        throw "Could not read configVersion from $root. $($_.Exception.Message)"
    }
    $version = [string]$info.configVersion
    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "Server at $root did not return configVersion."
    }
    return $version
}

function Assert-PublishedConfigAlignment {
    $published = Get-PublishedConfigIdentity
    Write-Host "[CONFIG] Published server/client version $($published.Version)"
    return $published
}

function Assert-RunningConfigAlignment([string]$Url, $Published = $null) {
    if ($null -eq $Published) { $Published = Get-PublishedConfigIdentity }
    $actual = Get-RunningConfigVersion $Url
    if ($actual -ne $Published.Version) {
        throw "Running server config '$actual' does not match client '$($Published.Version)'."
    }
    Write-Host "[CONFIG] Running server matches client $($Published.Version)"
    return $actual
}
