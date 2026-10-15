param(
    [Parameter(Mandatory=$true)][string]$InputDocx,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskAllowedInput = Join-Path $taskRepository 'outputs\strategic-final-uat-20261014'
$taskAllowedOutput = Join-Path $taskRepository 'outputs\.qa\strategic-final-uat'
$taskSource = [IO.Path]::GetFullPath($InputDocx)
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $taskSource.StartsWith($taskAllowedInput + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($taskSource) -ne '.docx') {
    throw 'Expected strategic UAT DOCX in the explicitly scoped output directory'
}
if (-not $taskOutput.StartsWith($taskAllowedOutput + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Expected private strategic UAT QA directory'
}
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskPdf = Join-Path $taskOutput ([IO.Path]::GetFileNameWithoutExtension($taskSource) + '.pdf')
$taskWord = $null
$taskDocument = $null
$taskOwnsWord = $false
try {
    $taskWord = New-Object -ComObject Word.Application
    if ($taskWord.Documents.Count -ne 0) { throw 'Refusing to change an existing user Word session' }
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
