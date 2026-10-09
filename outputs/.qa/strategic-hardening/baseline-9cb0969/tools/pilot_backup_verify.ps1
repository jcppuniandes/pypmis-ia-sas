param(
  [string]$BackupDir
)

$ErrorActionPreference = "Stop"

if (-not $BackupDir) {
  $latest = Get-ChildItem -Path ".\backups\pilot" -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($null -eq $latest) {
    throw "No backup directory was found under .\backups\pilot."
  }
  $BackupDir = $latest.FullName
}

$resolvedBackupDir = Resolve-Path -Path $BackupDir
$manifestPath = Join-Path $resolvedBackupDir "manifest.json"
if (-not (Test-Path $manifestPath)) {
  throw "manifest.json was not found in $resolvedBackupDir."
}

$manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
$dbBackup = Join-Path $resolvedBackupDir $manifest.database_backup
$documentBackup = Join-Path $resolvedBackupDir $manifest.document_storage_backup

if (-not (Test-Path $dbBackup)) {
  throw "Database backup was not found: $dbBackup"
}
if (-not (Test-Path $documentBackup)) {
  throw "Document storage backup was not found: $documentBackup"
}

Write-Host "== Pilot backup verify =="
Write-Host "Backup: $resolvedBackupDir"

$dbTmpName = "verify-$($manifest.database_backup)"
docker compose cp $dbBackup "db:/tmp/$dbTmpName"
try {
  docker compose exec -T db pg_restore -l "/tmp/$dbTmpName" | Out-Null
} finally {
  docker compose exec -T db rm "/tmp/$dbTmpName" | Out-Null
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($documentBackup)
try {
  foreach ($entry in $zip.Entries) {
    if ($entry.FullName.Contains("..")) {
      throw "Document backup contains unsafe entry path: $($entry.FullName)"
    }
  }
  $entryCount = $zip.Entries.Count
} finally {
  $zip.Dispose()
}

$dbSize = (Get-Item $dbBackup).Length
$documentSize = (Get-Item $documentBackup).Length
if ($dbSize -le 0) {
  throw "Database backup is empty."
}
if ($documentSize -le 0) {
  throw "Document storage backup is empty."
}

Write-Host "OK Database dump is readable by pg_restore -l"
Write-Host "OK Document ZIP opens and has $entryCount entries"
Write-Host "OK Backup sizes: DB $dbSize bytes / documents $documentSize bytes"
Write-Host "OK Pilot backup verify completed"
