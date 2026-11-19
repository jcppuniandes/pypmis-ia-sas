param([Parameter(Mandatory=$true)][ValidateSet('microclose','final')][string]$Kind, [string]$RenderName = '')
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$qa = Join-Path $repo 'outputs\.qa\wave-o2c-20261118'
$name = if ($Kind -eq 'microclose') { 'P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report1' } else { 'P&Pmis_Wave_O2C_Contracts_Commitments_Technical_Report' }
$source = Join-Path $qa "$Kind-candidate\$name.docx"
$dir = Join-Path $qa $(if ($RenderName) { $RenderName } else { "$Kind-word-render" })
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$pdf = Join-Path $dir "$name.pdf"
if (Test-Path -LiteralPath $pdf) { throw 'The selected Word export already exists' }
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
    if ((Get-FileHash -LiteralPath $source).Hash -ne $sha) { throw 'Word candidate changed' }
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
