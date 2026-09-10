param(
    [ValidateSet('Start', 'Stop', 'Build')]
    [string]$Action = 'Start'
)

$ErrorActionPreference = 'Stop'
$serverRoot = $PSScriptRoot
$projectRoot = Join-Path $serverRoot 'src/FantasyCard.Server'
$projectFile = Join-Path $projectRoot 'FantasyCard.Server.csproj'
$buildRoot = Join-Path $serverRoot '.artifacts/local-build'
$stateRoot = Join-Path $serverRoot '.artifacts/local-server'
$stateFile = Join-Path $stateRoot 'state.json'
$stdoutFile = Join-Path $stateRoot 'stdout.log'
$stderrFile = Join-Path $stateRoot 'stderr.log'
$startedProcess = $null
$stateWritten = $false
$lifecycleLock = $null

function Read-ServerState {
    if (!(Test-Path -LiteralPath $stateFile)) { return $null }
    try {
        $saved = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ([int]$saved.pid -le 0 -or !$saved.startTimeUtc -or !$saved.healthUrl) {
            throw 'Missing process identity.'
        }
        [void][DateTime]::Parse($saved.startTimeUtc)
        return $saved
    } catch {
        throw "Cannot read server process identity from $stateFile. $($_.Exception.Message)"
    }
}

function Get-RecordedProcess($Saved) {
    if ($null -eq $Saved) { return $null }
    if (![string]::Equals([string]$Saved.projectRoot, $projectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    $ownedProcess = Get-Process -Id ([int]$Saved.pid) -ErrorAction SilentlyContinue
    if ($null -eq $ownedProcess) { return $null }
    # A copied state file or reused PID must never identify another process as ours.
    $expectedStart = [DateTime]::Parse($Saved.startTimeUtc).ToUniversalTime()
    if ($ownedProcess.StartTime.ToUniversalTime().Ticks -ne $expectedStart.Ticks) {
        return $null
    }
    return $ownedProcess
}

function Test-Ready([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Get-HealthUrl([string]$Urls) {
    $localAddresses = @('localhost', '127.0.0.1', '::1', $env:COMPUTERNAME)
    foreach ($network in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        foreach ($address in $network.GetIPProperties().UnicastAddresses) {
            $localAddresses += $address.Address.ToString()
        }
    }
    $candidates = @()
    foreach ($binding in $Urls.Split(';')) {
        $normalized = $binding.Trim() -replace '://(\*|\+|0\.0\.0\.0|\[::\])(?=:|/|$)', '://127.0.0.1'
        $uri = $null
        if ([Uri]::TryCreate($normalized, [UriKind]::Absolute, [ref]$uri) -and
            $uri.Scheme -in @('http', 'https') -and
            ($uri.IsLoopback -or $uri.DnsSafeHost -in $localAddresses)) {
            $candidates += $uri
        }
    }
    if ($candidates.Count -eq 0) {
        throw 'ASPNETCORE_URLS must include a local HTTP or HTTPS address for the readiness check.'
    }
    $selected = $candidates | Sort-Object @{ Expression = { $_.Scheme -ne 'http' } } | Select-Object -First 1
    return $selected.GetLeftPart([UriPartial]::Authority) + '/health/ready'
}

function Test-PortInUse([string]$Url) {
    $uri = [Uri]$Url
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync($uri.DnsSafeHost, $uri.Port)
        return $connection.Wait(500) -and $client.Connected
    } catch { return $false }
    finally { $client.Dispose() }
}

function Build-Server {
    $dotnetCommand = Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $dotnetCommand) {
        throw 'The .NET SDK was not found. Install the SDK required by server/global.json and reopen the terminal.'
    }
    $script:dotnetPath = $dotnetCommand.Source
    # Running in serverRoot lets the SDK resolver enforce global.json and its roll-forward policy.
    $resolvedSdk = & $script:dotnetPath --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "No compatible .NET SDK was found for server/global.json. $($resolvedSdk -join [Environment]::NewLine)"
    }
    Write-Host "[BUILD] Using .NET SDK $resolvedSdk"
    & $script:dotnetPath build $projectFile --artifacts-path $buildRoot --force --no-incremental '-p:WarningsNotAsErrors=NU1900'
    if ($LASTEXITCODE -ne 0) { throw 'Server build failed. Review the build errors above.' }
    $outputRoot = Join-Path $buildRoot 'bin/FantasyCard.Server'
    $assemblies = @(Get-ChildItem -LiteralPath $outputRoot -Filter 'FantasyCard.Server.dll' -File -Recurse)
    if ($assemblies.Count -ne 1) { throw "Expected one server assembly under $outputRoot." }
    $script:serverDll = $assemblies[0].FullName
}

function Show-ServerLogs {
    foreach ($logFile in @($stdoutFile, $stderrFile)) {
        if (Test-Path -LiteralPath $logFile) {
            Write-Host "[LOG] $logFile"
            Get-Content -LiteralPath $logFile -Tail 30 | Out-Host
        }
    }
}

Push-Location $serverRoot
try {
    [void](New-Item -ItemType Directory -Path $stateRoot -Force)
    try {
        # Serialize double-clicks and stop/update operations for this checkout.
        $lifecycleLock = [IO.File]::Open((Join-Path $stateRoot 'lifecycle.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch [IO.IOException] {
        throw 'Another local server start, stop, or build is in progress. Wait for it to finish.'
    }
    if ($Action -eq 'Stop') {
        $saved = Read-ServerState
        $ownedProcess = Get-RecordedProcess $saved
        if ($null -ne $ownedProcess) {
            Stop-Process -InputObject $ownedProcess -ErrorAction Stop
            if (!$ownedProcess.WaitForExit(15000)) { throw 'The server process did not stop within 15 seconds.' }
            Write-Host '[STOPPED] Local server stopped. PostgreSQL remains running and its data is preserved.'
        } else {
            Write-Host '[STOPPED] No matching local server process is running. PostgreSQL is unchanged.'
        }
        if ($null -ne $saved) { Remove-Item -LiteralPath $stateFile -Force }
        exit 0
    }

    if ($Action -eq 'Build') {
        if ($null -ne (Get-RecordedProcess (Read-ServerState))) {
            throw 'Stop the local server with stop-server.bat before updating its build.'
        }
        Build-Server
        Write-Host '[UPDATED] Local server build completed.'
        exit 0
    }

    $saved = Read-ServerState
    $ownedProcess = Get-RecordedProcess $saved
    if ($null -ne $ownedProcess) {
        if (!(Test-Ready $saved.healthUrl)) {
            Show-ServerLogs
            throw 'The recorded server is running but is not ready. Inspect the logs, or stop it before restarting.'
        }
        Write-Host "[READY] Local server is already running: $($saved.healthUrl)"
        exit 0
    }
    if ($null -ne $saved) { Remove-Item -LiteralPath $stateFile -Force }

    if ([string]::IsNullOrWhiteSpace($env:ASPNETCORE_URLS)) {
        $env:ASPNETCORE_URLS = 'http://127.0.0.1:5080'
    }
    $healthUrl = Get-HealthUrl $env:ASPNETCORE_URLS
    if (Test-PortInUse $healthUrl) {
        throw "The port at $healthUrl is already in use by an unowned process. Stop that service or set ASPNETCORE_URLS to another local port."
    }

    Build-Server
    [void](New-Item -ItemType Directory -Path $stateRoot -Force)
    $env:ASPNETCORE_ENVIRONMENT = 'Development'
    $env:DOTNET_ENVIRONMENT = 'Development'
    Write-Host '[START] Connecting to the configured PostgreSQL database. The database must already be running.'
    # Start-Process joins ArgumentList; quote each filesystem argument for paths containing spaces.
    $launchArguments = @(('"{0}"' -f $script:serverDll), '--contentRoot', ('"{0}"' -f $projectRoot))
    $startedProcess = Start-Process -FilePath $script:dotnetPath -ArgumentList $launchArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
    $saved = [ordered]@{
        projectRoot = $projectRoot
        pid = $startedProcess.Id
        startTimeUtc = $startedProcess.StartTime.ToUniversalTime().ToString('o')
        healthUrl = $healthUrl
    }
    $saved | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding ASCII
    $stateWritten = $true

    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $startedProcess.Refresh()
        if ($startedProcess.HasExited) {
            throw "The server exited before becoming ready (exit code $($startedProcess.ExitCode))."
        }
        if (Test-Ready $healthUrl) {
            if ($null -eq (Get-RecordedProcess (Read-ServerState))) {
                throw 'The server exited during the readiness check.'
            }
            Write-Host "[READY] Local server is running: $healthUrl"
            Write-Host "[LOGS] $stateRoot"
            exit 0
        }
        Start-Sleep -Seconds 1
    }
    throw 'The server did not become ready within 60 seconds. Check PostgreSQL connectivity and the server logs.'
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    if ($null -ne $startedProcess) {
        $startedProcess.Refresh()
        if (!$startedProcess.HasExited) {
            Stop-Process -InputObject $startedProcess -ErrorAction SilentlyContinue
        }
        if ($stateWritten) {
            Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
        }
        Show-ServerLogs
    }
    exit 1
} finally {
    if ($null -ne $lifecycleLock) { $lifecycleLock.Dispose() }
    Pop-Location
}
