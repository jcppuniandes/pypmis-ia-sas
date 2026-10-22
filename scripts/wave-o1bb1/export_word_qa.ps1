param([Parameter(Mandatory=$true)][string]$InputDocx, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskInputRoot = Join-Path $taskRepository 'outputs\wave-o1bb1-20261021'
$taskQaRoot = Join-Path $taskRepository 'outputs\.qa\wave-o1bb1-20261021'
$taskSource = [IO.Path]::GetFullPath($InputDocx)
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $taskSource.StartsWith($taskInputRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($taskSource) -ne '.docx') { throw 'Expected scoped B1 DOCX' }
if (-not $taskOutput.StartsWith($taskQaRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected private B1 QA directory' }
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskPdf = Join-Path $taskOutput ([IO.Path]::GetFileNameWithoutExtension($taskSource) + '.pdf')
$taskWord = $null
$taskDocument = $null
$taskOwnsWord = $false
$taskInputSha = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
try {
    $taskWord = New-Object -ComObject Word.Application
    if ($taskWord.Documents.Count -ne 0) { throw 'Refusing to change existing Word documents' }
    $taskOwnsWord = $true
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskWord.AutomationSecurity = 3
    $taskDocument = $taskWord.Documents.Open($taskSource, $false, $true, $false)
    $taskDocument.Fields.Update() | Out-Null
    $taskDocument.Repaginate()
    $taskDocument.ExportAsFixedFormat($taskPdf, 17)
    if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInputSha) { throw 'DOCX changed during export' }
    $taskProof = [ordered]@{ input_docx=$taskSource; input_docx_sha256=$taskInputSha; output_pdf=$taskPdf; output_pdf_sha256=(Get-FileHash -LiteralPath $taskPdf -Algorithm SHA256).Hash.ToLowerInvariant(); read_only=$true; pages=$taskDocument.ComputeStatistics(2) }
    [IO.File]::WriteAllText($taskPdf + '.export.json', ($taskProof | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
    Write-Output ($taskProof | ConvertTo-Json -Compress)
} finally {
    if ($null -ne $taskDocument) { $taskDocument.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDocument) | Out-Null }
    if ($null -ne $taskWord) {
        if ($taskOwnsWord -and $taskWord.Documents.Count -eq 0) { $taskWord.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWord) | Out-Null
    }
}
