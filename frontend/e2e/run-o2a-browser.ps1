[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $Fixture,
  [Parameter(Mandatory)] [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$resolvedFixture = (Resolve-Path -LiteralPath $Fixture).Path
$resolvedOutput = (New-Item -ItemType Directory -Force -Path $OutputDirectory).FullName
$snapshotScript = @'
const { execFileSync } = require('node:child_process');
const { readFileSync, existsSync } = require('node:fs');
const { createHash } = require('node:crypto');
const path = require('node:path');
const roots = ['backend/app', 'backend/alembic', 'backend/tests', 'frontend/src',
  'frontend/e2e/engineering-foundation.spec.ts', 'frontend/package.json', 'frontend/package-lock.json',
  'frontend/tsconfig.json', 'frontend/vite.config.ts', 'frontend/eslint.config.js', 'frontend/playwright.config.ts',
  'frontend/vitest.setup.ts'];
const files = execFileSync('git', ['ls-files', '-z', '-co', '--exclude-standard', '--', ...roots],
  { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).split('\0');
const snapshot = Object.fromEntries([...new Set(files)].sort().filter((file) => file && existsSync(file) &&
  (file.startsWith('frontend/') || /\.(py|json|xml|xer|csv)$/i.test(path.extname(file))))
  .map((file) => [file, createHash('sha256').update(readFileSync(file)).digest('hex')]));
process.stdout.write(JSON.stringify(snapshot));
'@

Push-Location $repoRoot
try {
  $collector = Join-Path $repoRoot 'scripts\wave-o2a\collect_release_evidence.py'
  $python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
  $useCollector = (Test-Path -LiteralPath $collector) -and (Test-Path -LiteralPath $python)
  function Get-O2ASnapshot {
    if ($useCollector) {
      $snapshot = & $python $collector --snapshot-source browser
    } else {
      $snapshot = $snapshotScript | & node
    }
    if ($LASTEXITCODE -ne 0) { throw "Source snapshot failed: $LASTEXITCODE" }
    return (($snapshot -join "`n") | ConvertFrom-Json -AsHashtable)
  }

  $before = Get-O2ASnapshot
  $started = (Get-Date).ToUniversalTime().ToString('o')
  $env:E2E_O2A_FIXTURE = $resolvedFixture
  $env:E2E_O2A_OUTPUT = $resolvedOutput
  $env:E2E_API_URL = 'http://127.0.0.1:8859'
  $env:E2E_BASE_URL = 'http://127.0.0.1:5519'
  Push-Location (Join-Path $repoRoot 'frontend')
  try {
    $traces = Join-Path $resolvedOutput 'playwright-results'
    & .\node_modules\.bin\playwright.cmd test e2e/engineering-foundation.spec.ts --project=chromium --workers=1 --reporter=line --output $traces 2>&1 | Tee-Object -FilePath (Join-Path $resolvedOutput 'playwright.log')
    $browserExit = $LASTEXITCODE
  } finally { Pop-Location }

  $after = Get-O2ASnapshot
  $same = $before.Count -eq $after.Count
  foreach ($entry in $before.GetEnumerator()) {
    if ($after[$entry.Key] -ne $entry.Value) { $same = $false; Write-Warning "Source changed: $($entry.Key)" }
  }
  $browserResult = Join-Path $resolvedOutput 'browser-uat.json'
  $performanceResult = Join-Path $resolvedOutput 'performance.json'
  $filesExist = (Test-Path -LiteralPath $browserResult) -and (Test-Path -LiteralPath $performanceResult)
  $passed = $browserExit -eq 0 -and $same -and $filesExist -and
    ((Get-Content -LiteralPath $browserResult -Raw | ConvertFrom-Json).result -eq 'PASS')
  $proof = [ordered]@{
    result = $(if ($passed) { 'PASS' } else { 'FAIL' })
    playwright_exit_code = $browserExit
    source_unchanged_during_validation = $same
    source_sha256 = $after
    browser_uat_sha256 = $(if ($filesExist) { (Get-FileHash -LiteralPath $browserResult -Algorithm SHA256).Hash.ToLowerInvariant() })
    performance_sha256 = $(if ($filesExist) { (Get-FileHash -LiteralPath $performanceResult -Algorithm SHA256).Hash.ToLowerInvariant() })
    started_at = $started
    completed_at = (Get-Date).ToUniversalTime().ToString('o')
  }
  $proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'browser-source-proof.json') -Encoding utf8NoBOM
  if (!$passed) { exit 1 }
} finally { Pop-Location }
