[CmdletBinding()]
param([Parameter(Mandatory)] [string] $OutputDirectory)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$resolvedOutput = (New-Item -ItemType Directory -Force -Path $OutputDirectory).FullName
$collector = Join-Path $repoRoot 'scripts\wave-o2a\collect_release_evidence.py'
$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'

function Get-FrontendSnapshot {
  $snapshot = & $python $collector --snapshot-source frontend
  if ($LASTEXITCODE -ne 0) { throw "Source snapshot failed: $LASTEXITCODE" }
  return (($snapshot -join "`n") | ConvertFrom-Json -AsHashtable)
}

$checks = @(
  @{ name = 'Prettier'; log = 'frontend-prettier.log'; executable = 'prettier'; args = @('--check', 'src/', 'e2e/engineering-foundation.spec.ts') },
  @{ name = 'ESLint'; log = 'frontend-eslint.log'; executable = 'eslint'; args = @('src/', '--max-warnings=10') },
  @{ name = 'TypeScript'; log = 'frontend-tsc.log'; executable = 'tsc'; args = @('--noEmit') },
  @{ name = 'Vitest O2A'; log = 'frontend-vitest.log'; executable = 'vitest'; args = @('run', 'src/features/engineering-foundation/engineeringFoundation.test.tsx', '--maxWorkers=1', '--minWorkers=1') }
)

$before = Get-FrontendSnapshot
$started = (Get-Date).ToUniversalTime().ToString('o')
$outcomes = @()
Push-Location (Join-Path $repoRoot 'frontend')
try {
  foreach ($check in $checks) {
    Write-Output "Running $($check.name)"
    $arguments = $check.args
    $log = Join-Path $resolvedOutput $check.log
    $executable = Join-Path '.\node_modules\.bin' "$($check.executable).cmd"
    & $executable @arguments 2>&1 | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
    if (!(Test-Path -LiteralPath $log)) { "No diagnostic output; process exit $exitCode" | Set-Content -LiteralPath $log }
    $outcomes += [ordered]@{ name = $check.name; log = $check.log; exit_code = $exitCode }
  }
} finally { Pop-Location }
$after = Get-FrontendSnapshot
$same = $before.Count -eq $after.Count
foreach ($entry in $before.GetEnumerator()) {
  if ($after[$entry.Key] -ne $entry.Value) { $same = $false; Write-Warning "Source changed: $($entry.Key)" }
}
$passed = $same -and @($outcomes | Where-Object { $_.exit_code -ne 0 }).Count -eq 0
$proof = [ordered]@{
  result = $(if ($passed) { 'PASS' } else { 'FAIL' })
  source_unchanged_during_validation = $same
  source_sha256 = $after
  checks = $outcomes
  started_at = $started
  completed_at = (Get-Date).ToUniversalTime().ToString('o')
}
$proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'frontend-validation.json') -Encoding utf8NoBOM
if (!$passed) { exit 1 }
