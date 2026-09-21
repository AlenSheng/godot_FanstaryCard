param(
    [string]$Godot = $env:GODOT_BIN,
    [string]$ProjectPath = (Join-Path $PSScriptRoot '..\\client'),
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\\builds\\android\\Relicbound.aab')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Require-Value([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Missing required release signing value: $Name. Set the corresponding Godot Android keystore environment variable before exporting."
    }
}

if ([string]::IsNullOrWhiteSpace($Godot)) {
    $Godot = 'godot'
}
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    throw "Godot project was not found: $ProjectPath"
}

Require-Value 'GODOT_ANDROID_KEYSTORE_RELEASE_PATH' $env:GODOT_ANDROID_KEYSTORE_RELEASE_PATH
Require-Value 'GODOT_ANDROID_KEYSTORE_USER' $env:GODOT_ANDROID_KEYSTORE_USER
Require-Value 'GODOT_ANDROID_KEYSTORE_PASSWORD' $env:GODOT_ANDROID_KEYSTORE_PASSWORD

$presetPath = Join-Path $ProjectPath 'export_presets.cfg'
$preset = Get-Content -LiteralPath $presetPath -Raw
foreach ($required in @(
    'name="Android Production"',
    'export_path="../builds/android/Relicbound.aab"',
    'gradle_build/use_gradle_build=true',
    'gradle_build/export_format=1',
    'gradle_build/target_sdk=36',
    'package/unique_name="com.relicbound.game"',
    'package/signed=true',
    'architectures/arm64-v8a=true'
)) {
    if ($preset -notmatch [regex]::Escape($required)) {
        throw "Android Production preset is missing: $required"
    }
}

$projectSettings = Get-Content -LiteralPath (Join-Path $ProjectPath 'project.godot') -Raw
if ($projectSettings -notmatch '(?m)^server_url="https://[^"\r\n]+"$') {
    throw 'Production project settings must contain an HTTPS platform/server_url.'
}
$gateway = Get-Content -LiteralPath (Join-Path $ProjectPath 'network/gateway.gd') -Raw
if ($gateway -notmatch 'if not OS\.is_debug_build\(\):') {
    throw 'Production gateway hardening is missing: the release client must ignore launch server overrides.'
}
$store = Get-Content -LiteralPath (Join-Path $ProjectPath 'state/game_store.gd') -Raw
if ($store -notmatch '正式客户端只能连接官方服务器') {
    throw 'Production login hardening is missing: arbitrary server addresses must be rejected.'
}
if ($projectSettings -match '(?i)(publisher.?key|admin.?api.?key|private.?key)\s*=') {
    throw 'Private server credentials must not be stored in client project settings.'
}

& $Godot --headless --path $ProjectPath --editor --quit
if ($LASTEXITCODE -ne 0) { throw "Godot project validation failed with exit code $LASTEXITCODE." }

& $Godot --headless --path $ProjectPath --export-release 'Android Production' $OutputPath
if ($LASTEXITCODE -ne 0) { throw "Android Production AAB export failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Godot reported a successful export but the AAB was not found: $OutputPath"
}

$file = Get-Item -LiteralPath $OutputPath
if ($file.Length -lt 1024) {
    throw "The exported AAB is unexpectedly small ($($file.Length) bytes): $OutputPath"
}
Write-Host "Android Production AAB ready: $($file.FullName) ($($file.Length) bytes)"
