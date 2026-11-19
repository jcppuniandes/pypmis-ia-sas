param([Parameter(Mandatory=$true)][string]$RenderName)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$qa = Join-Path $repo 'outputs\.qa\wave-o3a-20261118'
$name = 'P&Pmis_Wave_O3A_Construction_Field_Operations_Technical_Report'
$source = Join-Path $repo "outputs\wave-o3a-construction-field-operations-20261119\$name.docx"
$dir = Join-Path $qa $RenderName
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$pdf = Join-Path $dir "$name.pdf"
if (Test-Path -LiteralPath $pdf) { throw 'The selected export already exists' }
$sha = (Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant()
$word = $doc = $null
$owns = $false
try {
    $word = New-Object -ComObject Word.Application
    if ($word.Documents.Count -ne 0) { throw 'Will not touch open Word documents' }
    $owns = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $doc = $word.Documents.Open($source, $false, $true, $false)
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    $doc.ExportAsFixedFormat($pdf, 17)
    if ((Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant() -ne $sha) { throw 'Word source changed' }
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
