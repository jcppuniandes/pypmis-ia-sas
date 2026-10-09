param(
    [Parameter(Mandatory = $true)][string]$DocumentPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [ValidatePattern('^[A-Za-z0-9_-]+\.pdf$')][string]$PdfFileName = 'wave3a-word-native.pdf'
)
$ErrorActionPreference = 'Stop'
$taskWorkspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskInput = (Resolve-Path -LiteralPath $DocumentPath).Path
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $taskInput.StartsWith($taskWorkspace + '\', [StringComparison]::OrdinalIgnoreCase) -or
    -not $taskOutput.StartsWith($taskWorkspace + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Document QA targets must remain inside this workspace.'
}
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskPdf = Join-Path $taskOutput $PdfFileName
$taskWord = $null
$taskDocument = $null
try {
    # Create a dedicated automation instance; never attach to the user's active Word.
    $taskWord = New-Object -ComObject Word.Application
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskDocument = $taskWord.Documents.Open($taskInput, $false, $true, $false)
    $taskDocument.Fields.Update() | Out-Null
    $taskDocument.Repaginate()
    $taskPages = $taskDocument.ComputeStatistics(2)
    $taskDocument.ExportAsFixedFormat($taskPdf, 17)
    Write-Output "renderer=Microsoft Word; pages=$taskPages; pdf=$taskPdf"
} finally {
    if ($null -ne $taskDocument) {
        $taskDocument.Close(0)
        [Runtime.InteropServices.Marshal]::ReleaseComObject($taskDocument) | Out-Null
    }
    if ($null -ne $taskWord) {
        $taskWord.Quit()
        [Runtime.InteropServices.Marshal]::ReleaseComObject($taskWord) | Out-Null
    }
}
