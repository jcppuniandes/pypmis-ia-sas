param([Parameter(Mandatory=$true)][string]$InputDocx, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$o2Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$o2Source = [IO.Path]::GetFullPath($InputDocx)
$o2Qa = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $o2Source.StartsWith((Join-Path $o2Root 'outputs\wave-o2-20261109\'), [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($o2Source) -ne '.docx') { throw 'Expected scoped O2 DOCX' }
if (-not $o2Qa.StartsWith((Join-Path $o2Root 'outputs\.qa\wave-o2-20261109\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected private O2 QA directory' }
New-Item -ItemType Directory -Path $o2Qa -Force | Out-Null
$o2Pdf = Join-Path $o2Qa ([IO.Path]::GetFileNameWithoutExtension($o2Source) + '.pdf')
if (Test-Path -LiteralPath $o2Pdf) { throw 'Use a new QA iteration directory' }
$o2Before = (Get-FileHash -LiteralPath $o2Source -Algorithm SHA256).Hash.ToLowerInvariant()
$o2Word = $null
$o2Doc = $null
$o2OwnsWord = $false
try {
    $o2Word = New-Object -ComObject Word.Application
    if ($o2Word.Documents.Count -ne 0) { throw 'Refusing to affect existing Word documents' }
    $o2OwnsWord = $true
    $o2Word.Visible = $false
    $o2Word.DisplayAlerts = 0
    $o2Word.AutomationSecurity = 3
    $o2Doc = $o2Word.Documents.Open($o2Source, $false, $true, $false)
    $o2Doc.Fields.Update() | Out-Null
    $o2Doc.Repaginate()
    $o2Doc.ExportAsFixedFormat($o2Pdf, 17)
    if ((Get-FileHash -LiteralPath $o2Source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $o2Before) { throw 'DOCX changed during read-only export' }
    $o2Proof = [ordered]@{ input_docx=$o2Source; input_docx_sha256=$o2Before; output_pdf=$o2Pdf; output_pdf_sha256=(Get-FileHash -LiteralPath $o2Pdf -Algorithm SHA256).Hash.ToLowerInvariant(); read_only=$true; pages=$o2Doc.ComputeStatistics(2) }
    [IO.File]::WriteAllText($o2Pdf + '.export.json', ($o2Proof | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
    Write-Output ($o2Proof | ConvertTo-Json -Compress)
} finally {
    if ($null -ne $o2Doc) { $o2Doc.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($o2Doc) | Out-Null }
    if ($null -ne $o2Word) {
        if ($o2OwnsWord -and $o2Word.Documents.Count -eq 0) { $o2Word.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($o2Word) | Out-Null
    }
}
