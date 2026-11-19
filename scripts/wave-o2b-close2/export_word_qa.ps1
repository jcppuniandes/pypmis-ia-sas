param([Parameter(Mandatory=$true)][string]$Iteration)
$ErrorActionPreference = 'Stop'
if ($Iteration -notmatch '^word-render-[1-9][0-9]*$') { throw 'Expected a new word-render-N iteration' }
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$artifacts = Join-Path $repo 'outputs\.qa\wave-o2b-close2-20261112\artifacts'
$name = 'P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report1'
$source = Join-Path $artifacts "candidate\$name.docx"
$qa = Join-Path $artifacts $Iteration
New-Item -ItemType Directory -Path $qa -Force | Out-Null
$pdf = Join-Path $qa "$name.pdf"
if (Test-Path -LiteralPath $pdf) { throw 'Use a new QA iteration directory' }
$sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$word = $null
$doc = $null
$owns = $false
try {
    $word = New-Object -ComObject Word.Application
    if ($word.Documents.Count -ne 0) { throw 'Existing Word documents will not be touched' }
    $owns = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $doc = $word.Documents.Open($source, $false, $true, $false)
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    $doc.ExportAsFixedFormat($pdf, 17)
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) { throw 'DOCX changed during QA export' }
    $proof = [ordered]@{ input_docx=$source; input_docx_sha256=$sha; output_pdf=$pdf; output_pdf_sha256=(Get-FileHash -LiteralPath $pdf -Algorithm SHA256).Hash.ToLowerInvariant(); read_only=$true; pages=$doc.ComputeStatistics(2) }
    [IO.File]::WriteAllText($pdf + '.export.json', ($proof | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    $proof | ConvertTo-Json -Compress
} finally {
    if ($null -ne $doc) { $doc.Close(0); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) | Out-Null }
    if ($null -ne $word) {
        if ($owns -and $word.Documents.Count -eq 0) { $word.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
    }
}
