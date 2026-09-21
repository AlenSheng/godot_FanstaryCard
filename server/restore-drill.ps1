param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath,
    [string]$TargetDatabase = 'fantasycard_restore_drill',
    [switch]$KeepDatabase
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $DumpPath -PathType Leaf)) {
    throw "Backup dump was not found: $DumpPath"
}
if ($TargetDatabase -notmatch '^fantasycard_restore_drill(_[a-z0-9-]+)?$') {
    throw "TargetDatabase must be a disposable name beginning with fantasycard_restore_drill."
}

foreach ($tool in @('pg_restore', 'createdb', 'dropdb', 'psql')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "PostgreSQL client tool was not found: $tool"
    }
}

& pg_restore --list $DumpPath | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The dump archive failed pg_restore --list validation." }

& dropdb --if-exists $TargetDatabase
if ($LASTEXITCODE -ne 0) { throw "Could not clear the disposable restore database: $TargetDatabase" }
& createdb $TargetDatabase
if ($LASTEXITCODE -ne 0) { throw "Could not create the disposable restore database: $TargetDatabase" }

try {
    & pg_restore --exit-on-error --no-owner --no-privileges --dbname $TargetDatabase $DumpPath
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE." }
    $schema = (& psql --dbname $TargetDatabase --tuples-only --no-align --command "SELECT CASE WHEN to_regclass('public.players') IS NOT NULL AND to_regclass('public.schema_migrations') IS NOT NULL THEN 'ready' ELSE 'missing' END;").Trim()
    if ($schema -ne 'ready') { throw "Restored database is missing the players or schema_migrations table." }
    Write-Host "Restore drill passed: $TargetDatabase contains the expected schema."
}
finally {
    if (-not $KeepDatabase) {
        & dropdb --if-exists $TargetDatabase | Out-Null
    } else {
        Write-Host "Keeping disposable restore database: $TargetDatabase"
    }
}
