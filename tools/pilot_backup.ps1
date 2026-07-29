param(
  [string]$BackupRoot = ".\backups\pilot",
  [string]$DbUser = "pypmis",
  [string]$DbName = "pypmis"
)

$ErrorActionPreference = "Stop"

function Invoke-DockerChecked {
  param(
    [string[]]$Arguments
  )
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker command failed ($LASTEXITCODE): docker $($Arguments -join ' ')"
  }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedRoot = Resolve-Path -Path "."
$backupDir = Join-Path $BackupRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$dbBackupName = "pypmis-$timestamp.dump"
$documentBackupName = "document-storage-$timestamp.zip"
$manifestPath = Join-Path $backupDir "manifest.json"

Write-Host "== Pilot backup =="
Write-Host "Repository: $resolvedRoot"
Write-Host "Output: $backupDir"

Invoke-DockerChecked @("compose", "exec", "-T", "db", "pg_dump", "-U", $DbUser, "-d", $DbName, "-Fc", "-f", "/tmp/$dbBackupName")
Invoke-DockerChecked @("compose", "cp", "db:/tmp/$dbBackupName", (Join-Path $backupDir $dbBackupName))
Invoke-DockerChecked @("compose", "exec", "-T", "db", "rm", "/tmp/$dbBackupName")

$zipCommand = @"
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path('/app/storage/documents')
target = Path('/tmp/$documentBackupName')
with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
    if root.exists():
        for path in root.rglob('*'):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
"@

Invoke-DockerChecked @("compose", "exec", "-T", "api", "python", "-c", $zipCommand)
Invoke-DockerChecked @("compose", "cp", "api:/tmp/$documentBackupName", (Join-Path $backupDir $documentBackupName))
Invoke-DockerChecked @("compose", "exec", "-T", "api", "rm", "/tmp/$documentBackupName")

$manifest = [ordered]@{
  created_at = (Get-Date).ToString("s")
  database_backup = $dbBackupName
  document_storage_backup = $documentBackupName
  db_name = $DbName
  db_user = $DbUser
  note = "Pilot backup for controlled restore rehearsal. Validate restore in a separate environment before production use."
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding UTF8

Write-Host "OK Database backup: $(Join-Path $backupDir $dbBackupName)"
Write-Host "OK Document storage backup: $(Join-Path $backupDir $documentBackupName)"
Write-Host "OK Manifest: $manifestPath"
