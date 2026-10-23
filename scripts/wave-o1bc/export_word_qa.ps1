param([Parameter(Mandatory=$true)][string]$InputDocx, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$costRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$costInputRoot = Join-Path $costRepository 'outputs\wave-o1bc-20261022'
$costQaRoot = Join-Path $costRepository 'outputs\.qa\wave-o1bc-20261022'
$costSource = [IO.Path]::GetFullPath($InputDocx)
$costOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $costSource.StartsWith($costInputRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($costSource) -ne '.docx') { throw 'Expected scoped Cost DOCX' }
if (-not $costOutput.StartsWith($costQaRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected private Cost QA directory' }
New-Item -ItemType Directory -Path $costOutput -Force | Out-Null
$costPdf = Join-Path $costOutput ([IO.Path]::GetFileNameWithoutExtension($costSource) + '.pdf')
if (Test-Path -LiteralPath $costPdf) { throw 'Use a fresh private QA iteration directory' }
$costWord = $null
$costDocument = $null
$costOwnsWord = $false
$costInputSha = (Get-FileHash -LiteralPath $costSource -Algorithm SHA256).Hash.ToLowerInvariant()
try {
    $costWord = New-Object -ComObject Word.Application
    if ($costWord.Documents.Count -ne 0) { throw 'Refusing to change existing Word documents' }
    $costOwnsWord = $true
    $costWord.Visible = $false
    $costWord.DisplayAlerts = 0
    $costWord.AutomationSecurity = 3
    $costDocument = $costWord.Documents.Open($costSource, $false, $true, $false)
    $costDocument.Fields.Update() | Out-Null
    $costDocument.Repaginate()
    $costDocument.ExportAsFixedFormat($costPdf, 17)
    if ((Get-FileHash -LiteralPath $costSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $costInputSha) { throw 'DOCX changed during read-only export' }
    $costProof = [ordered]@{ input_docx=$costSource; input_docx_sha256=$costInputSha; output_pdf=$costPdf; output_pdf_sha256=(Get-FileHash -LiteralPath $costPdf -Algorithm SHA256).Hash.ToLowerInvariant(); read_only=$true; pages=$costDocument.ComputeStatistics(2) }
    [IO.File]::WriteAllText($costPdf + '.export.json', ($costProof | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
    Write-Output ($costProof | ConvertTo-Json -Compress)
} finally {
    if ($null -ne $costDocument) { $costDocument.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($costDocument) | Out-Null }
    if ($null -ne $costWord) {
        if ($costOwnsWord -and $costWord.Documents.Count -eq 0) { $costWord.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($costWord) | Out-Null
    }
}
