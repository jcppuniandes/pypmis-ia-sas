param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$RenderName)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$resolved = (Resolve-Path -LiteralPath $Source).Path
if (-not $resolved.StartsWith((Join-Path $repo 'outputs\'), [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($resolved) -ne '.docx') { throw 'Expected an output DOCX in this repository' }
$qa = Join-Path $repo 'outputs\.qa\wave-o3b-20261119'
$dir = Join-Path $qa $RenderName
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$pdf = Join-Path $dir ([IO.Path]::GetFileNameWithoutExtension($resolved) + '.pdf')
if (Test-Path -LiteralPath $pdf) { throw 'Preserve existing render' }
$sha = (Get-FileHash -LiteralPath $resolved).Hash.ToLowerInvariant()
$word = $doc = $null
$owns = $false
try {
    $word = New-Object -ComObject Word.Application
    if ($word.Documents.Count -ne 0) { throw 'Will not touch open Word documents' }
    $owns = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $doc = $word.Documents.Open($resolved, $false, $true, $false)
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    $doc.ExportAsFixedFormat($pdf, 17)
    if ((Get-FileHash -LiteralPath $resolved).Hash.ToLowerInvariant() -ne $sha) { throw 'Source DOCX changed' }
    $proof = @{ input_docx_sha256=$sha; output_pdf_sha256=(Get-FileHash -LiteralPath $pdf).Hash.ToLowerInvariant(); pages=$doc.ComputeStatistics(2) }
    [IO.File]::WriteAllText($pdf + '.export.json', ($proof | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $proof | ConvertTo-Json -Compress
} finally {
    if ($null -ne $doc) { $doc.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) | Out-Null }
    if ($null -ne $word) {
        if ($owns -and $word.Documents.Count -eq 0) { $word.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
    }
}
