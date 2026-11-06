param([Parameter(Mandatory=$true)][string]$InputDocx, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$progressRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$progressInputRoot = Join-Path $progressRepository 'outputs\wave-o1bd-20261104'
$progressQaRoot = Join-Path $progressRepository 'outputs\.qa\wave-o1bd-20261104'
$progressSource = [IO.Path]::GetFullPath($InputDocx)
$progressOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $progressSource.StartsWith($progressInputRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($progressSource) -ne '.docx') { throw 'Expected scoped Progress DOCX' }
if (-not $progressOutput.StartsWith($progressQaRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected private Progress QA directory' }
New-Item -ItemType Directory -Path $progressOutput -Force | Out-Null
$progressPdf = Join-Path $progressOutput ([IO.Path]::GetFileNameWithoutExtension($progressSource) + '.pdf')
if (Test-Path -LiteralPath $progressPdf) { throw 'Use a fresh private QA iteration directory' }
$progressWord = $null
$progressDocument = $null
$progressOwnsWord = $false
$progressInputSha = (Get-FileHash -LiteralPath $progressSource -Algorithm SHA256).Hash.ToLowerInvariant()
try {
    $progressWord = New-Object -ComObject Word.Application
    if ($progressWord.Documents.Count -ne 0) { throw 'Refusing to change existing Word documents' }
    $progressOwnsWord = $true
    $progressWord.Visible = $false
    $progressWord.DisplayAlerts = 0
    $progressWord.AutomationSecurity = 3
    $progressDocument = $progressWord.Documents.Open($progressSource, $false, $true, $false)
    $progressDocument.Fields.Update() | Out-Null
    $progressDocument.Repaginate()
    $progressDocument.ExportAsFixedFormat($progressPdf, 17)
    if ((Get-FileHash -LiteralPath $progressSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $progressInputSha) { throw 'DOCX changed during read-only export' }
    $progressProof = [ordered]@{ input_docx=$progressSource; input_docx_sha256=$progressInputSha; output_pdf=$progressPdf; output_pdf_sha256=(Get-FileHash -LiteralPath $progressPdf -Algorithm SHA256).Hash.ToLowerInvariant(); read_only=$true; pages=$progressDocument.ComputeStatistics(2) }
    [IO.File]::WriteAllText($progressPdf + '.export.json', ($progressProof | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
    Write-Output ($progressProof | ConvertTo-Json -Compress)
} finally {
    if ($null -ne $progressDocument) { $progressDocument.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($progressDocument) | Out-Null }
    if ($null -ne $progressWord) {
        if ($progressOwnsWord -and $progressWord.Documents.Count -eq 0) { $progressWord.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($progressWord) | Out-Null
    }
}
