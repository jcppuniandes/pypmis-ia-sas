param([switch]$SpecOnly)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$qa = Join-Path $repo 'outputs/.qa/wave-o1c-20261106'
$proofPath = Join-Path $qa 'frontend-validation.json'
$scoped = @(
    'src/features/forecast-foundation',
    'src/components/AdminConfigurationView.tsx',
    'src/features/awp/GovernedProfilesAdminView.tsx',
    'src/features/workspace-context/WorkspaceOperationalPage.tsx'
)

function Get-FrontendSources {
    $sources = [ordered]@{}
    $paths = git -C $repo ls-files --cached --others --exclude-standard -- frontend/src frontend/e2e/forecast-foundation.spec.ts frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/eslint.config.js frontend/playwright.config.ts frontend/vitest.setup.ts
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inventory frontend source' }
    foreach ($path in ($paths | Sort-Object -Unique)) {
        $file = Join-Path $repo $path
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            $sources[$path] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return $sources
}

function Invoke-FrontendCheck($name, $logName, [string[]]$nodeArgs) {
    $log = Join-Path $qa $logName
    $name | Set-Content -LiteralPath $log -Encoding utf8NoBOM
    & node @nodeArgs 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    $checkExit = $LASTEXITCODE
    "Exit code: $checkExit" | Add-Content -LiteralPath $log -Encoding utf8NoBOM
    return @{ name = $name; exit_code = $checkExit; log = $logName }
}

$sourceBefore = Get-FrontendSources
New-Item -ItemType Directory -Path $qa -Force | Out-Null
$retained = @()
$previousProofSha = $null
if ($SpecOnly) {
    $previous = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json -AsHashtable
    if ($previous.result -ne 'PASS' -or -not $previous.source_unchanged_during_validation) {
        throw 'A source-fresh full frontend PASS is required for a spec-only rerun'
    }
    $priorHashes = $previous.source_sha256
    if ($sourceBefore.Count -ne $priorHashes.Count) { throw 'Source inventory changed; run full validation' }
    foreach ($file in $sourceBefore.Keys) {
        if ($file -ne 'frontend/e2e/forecast-foundation.spec.ts' -and $sourceBefore[$file] -cne $priorHashes[$file]) {
            throw "Production or test source changed; run full validation: $file"
        }
    }
    $retained = @($previous.checks | Where-Object { $_.name -match '^(Vitest|ESLint|TypeScript)' })
    if ($retained.Count -ne 3 -or @($retained | Where-Object { $_.exit_code -ne 0 }).Count -ne 0) {
        throw 'Required prior frontend checks are missing or unsuccessful'
    }
    $previousProofSha = (Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
Push-Location (Join-Path $repo 'frontend')
try {
    $checks = if ($SpecOnly) {
        $retained
    } else {
        @(
            (Invoke-FrontendCheck 'Vitest scoped O1C' 'frontend-components.log' @('node_modules/vitest/vitest.mjs','run','src/features/forecast-foundation/forecastFoundation.test.tsx','--maxWorkers=1','--minWorkers=1','--reporter=default','--reporter=json',"--outputFile.json=$qa/frontend-components.json")),
            (Invoke-FrontendCheck 'ESLint scoped O1C production source and adapters' 'frontend-eslint.log' (@('node_modules/eslint/bin/eslint.js','--max-warnings=0') + $scoped)),
            (Invoke-FrontendCheck 'TypeScript project noEmit' 'frontend-typescript.log' @('node_modules/typescript/bin/tsc','--noEmit'))
        )
    }
    $checks += @(
        (Invoke-FrontendCheck 'Prettier scoped O1C including E2E' 'frontend-prettier.log' (@('node_modules/prettier/bin/prettier.cjs','--check') + $scoped + @('e2e/forecast-foundation.spec.ts'))),
        (Invoke-FrontendCheck 'Playwright O1C discovery without browser' 'frontend-e2e-discovery.log' @('node_modules/@playwright/test/cli.js','test','e2e/forecast-foundation.spec.ts','--project=chromium','--list'))
    )
} finally {
    Pop-Location
}
$sourceAfter = Get-FrontendSources
$unchanged = ($sourceBefore | ConvertTo-Json -Compress) -ceq ($sourceAfter | ConvertTo-Json -Compress)
$passed = $unchanged -and @($checks | Where-Object { $_.exit_code -ne 0 }).Count -eq 0
$proof = [ordered]@{
    result = $(if ($passed) { 'PASS' } else { 'FAIL' })
    source_unchanged_during_validation = $unchanged
    validation_mode = $(if ($SpecOnly) { 'SPEC_ONLY_UNCHANGED_PRODUCTION' } else { 'FULL' })
    retained_proof_sha256 = $previousProofSha
    checks = $checks
    source_sha256 = $sourceAfter
}
$proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $proofPath -Encoding utf8NoBOM
if (-not $passed) { exit 1 }
