# Launches a foreground Codex session. Does not fetch, switch, reset or deploy.
[CmdletBinding()]
param(
    [string]$RepoPath = (Join-Path $PSScriptRoot '..')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git was not found on PATH.'
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Codex CLI was not found. Open this worktree in the Codex app and use the prompt in PLAN.md.'
}
$repo = (Resolve-Path -LiteralPath $RepoPath).Path
$gitRoot = & git -C $repo rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) { throw 'RepoPath is not a Git worktree.' }
$repo = (Resolve-Path -LiteralPath $gitRoot).Path
$remote = & git -C $repo remote get-url origin
if ($LASTEXITCODE -ne 0 -or $remote -notmatch '(?i)github[.]com[:/]AlenSheng/godot_FanstaryCard(?:[.]git)?/?$') {
    throw 'The origin remote does not match AlenSheng/godot_FanstaryCard.'
}
$branch = & git -C $repo branch --show-current
if ($LASTEXITCODE -ne 0 -or $branch -notlike 'codex/protobuf-migration-*') {
    throw 'Use an independent codex/protobuf-migration-* branch; release/main are not allowed.'
}
$plan = Join-Path $repo 'docs/network-protobuf-migration/PLAN.md'
if (-not (Test-Path -LiteralPath $plan -PathType Leaf)) { throw 'Migration PLAN.md is missing.' }
$dirty = @(& git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Git status.' }
if ($dirty.Count -gt 0) {
    throw 'Worktree has uncommitted changes. They were left untouched. Review them before starting or use a separate clean worktree.'
}
$head = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Unable to read HEAD.' }
Write-Host ('Worktree: ' + $repo)
Write-Host ('Branch: ' + $branch + '  HEAD: ' + $head)
& codex --version
if ($LASTEXITCODE -ne 0) { throw 'Codex version check failed.' }
$prompt = 'Read docs/network-protobuf-migration/PLAN.md. Execute section 4 using real subagents for all six roles and the stated dependency order; start implementation rather than stopping at a plan. Respect path ownership, existing approvals and sandbox settings. Record only actual returned agent IDs in execution-state.json. If spawning is unavailable, mark it blocked instead of simulating workers. Never deploy, push or merge release.'
# Model, network permission and sandbox/approval policy are intentionally unchanged.
& codex -C $repo $prompt
if ($LASTEXITCODE -ne 0) { throw ('Codex exited with code ' + $LASTEXITCODE) }
