param(
    [ValidatePattern('^browser-actual-[1-9][0-9]*$')]
    [string]$AttemptDirectory = 'browser-actual-1'
)

$ErrorActionPreference = 'Stop'

$repositoryPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$evidencePath = Join-Path $repositoryPath 'outputs\.qa\gate07j-controlled-class-b-rebuild'
$chainPath = Join-Path $evidencePath 'fresh-capital-owner-chain.json'
$attemptPath = Join-Path $evidencePath $AttemptDirectory
$nodePath = 'C:\Users\Ricardo\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'

if (Test-Path -LiteralPath $attemptPath) {
    throw "Preserve the existing $AttemptDirectory attempt; do not overwrite or automatically retry it."
}
$chain = Get-Content -LiteralPath $chainPath -Raw | ConvertFrom-Json
if ($chain.backend_chain -ne 'PASS') { throw 'Backend lifecycle is not yet complete; browser launch refused.' }
if ($chain.setup.tenant_id -ne 1 -or $chain.setup.tenant_slug -ne 'fresh-copper-1765b06813' -or
    $chain.setup.project_id -ne 4 -or $chain.setup.portfolio_id -ne 3) {
    throw 'The manifest is not the explicitly selected persistent reconstruction.'
}
foreach ($stage in @('A30_FID', 'A31_POST_FID', 'PROJECT_INITIALIZED_NOT_ACTIVATED', 'PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION')) {
    if (-not ($chain.stages | Where-Object { $_.stage -eq $stage -and $_.status -eq 'PASS' })) {
        throw "Missing real backend lifecycle checkpoint: $stage"
    }
}
$chainHashBefore = (Get-FileHash -LiteralPath $chainPath -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $attemptPath | Out-Null

$env:E2E_BASE_URL = 'http://127.0.0.1:5543'
$env:E2E_API_URL = 'http://127.0.0.1:8840'
$env:E2E_STRATEGIC_EVIDENCE_ROOT = $evidencePath
$env:E2E_STRATEGIC_FRESH_CHAIN = $chainPath
$env:E2E_STRATEGIC_FRESH_SETUP = Join-Path $evidencePath 'fresh-setup.json'
$env:E2E_STRATEGIC_FRESH_BROWSER_RESULT = Join-Path $attemptPath 'fresh-browser-result.json'
$env:PLAYWRIGHT_JUNIT_OUTPUT_FILE = Join-Path $attemptPath 'strategic-capital-current.xml'
$browserOutputPath = Join-Path $attemptPath 'chromium'

Push-Location (Join-Path $repositoryPath 'frontend')
try {
    & $nodePath 'node_modules/@playwright/test/cli.js' test 'e2e/strategic-capital-current.spec.ts' --project=chromium --workers=1 --retries=0 --reporter=line,junit --output $browserOutputPath
    $browserExit = $LASTEXITCODE
} finally {
    Pop-Location
}
if ((Get-FileHash -LiteralPath $chainPath -Algorithm SHA256).Hash -ne $chainHashBefore) {
    throw 'The backend manifest changed during the browser traversal; inspect it before claiming immutable provenance.'
}
Write-Output "browser_exit=$browserExit"
Write-Output "evidence=$attemptPath"
Write-Output "backend_manifest_sha256=$chainHashBefore"
exit $browserExit
