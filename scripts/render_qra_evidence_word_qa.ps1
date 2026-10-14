param(
    [Parameter(Mandatory=$true)][string]$InputDocx,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\outputs'))
$taskSource = [IO.Path]::GetFullPath($InputDocx)
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $taskSource.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($taskSource) -ne '.docx') { throw 'Expected task DOCX under outputs' }
if (-not $taskOutput.StartsWith((Join-Path $taskRoot '.qa\qra-evidence\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected private QRA evidence QA directory' }
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskPdf = Join-Path $taskOutput ([IO.Path]::GetFileNameWithoutExtension($taskSource) + '.pdf')
$taskWord = $null
$taskDocument = $null
$taskOwnsWord = $false
try {
    $taskWord = New-Object -ComObject Word.Application
    if ($taskWord.Documents.Count -ne 0) { throw 'Refusing to modify an existing Word session' }
    $taskOwnsWord = $true
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskWord.AutomationSecurity = 3
    $taskDocument = $taskWord.Documents.Open($taskSource, $false, $true, $false)
    $taskDocument.Repaginate()
    $taskDocument.ExportAsFixedFormat($taskPdf, 17)
    Write-Output "pdf=$taskPdf"
    Write-Output "pages=$($taskDocument.ComputeStatistics(2))"
} finally {
    if ($null -ne $taskDocument) {
        $taskDocument.Close(0)
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDocument) | Out-Null
    }
    if ($null -ne $taskWord) {
        if ($taskOwnsWord -and $taskWord.Documents.Count -eq 0) { $taskWord.Quit() }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWord) | Out-Null
    }
}
